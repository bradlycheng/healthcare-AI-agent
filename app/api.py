# app/api.py

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

from .agent import run_oru_pipeline
from .security import sanitize_text

import sys
# Force unbuffered stdout
sys.stdout.reconfigure(encoding='utf-8')

import os
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
print("DEBUG: API MODULE LOADED", flush=True)

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
# AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
# AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "healthcare2025")

app = FastAPI(title="Healthcare HL7 → FHIR Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Simple in-memory rate limiter: keys=IP, values=timestamp of last LLM request
# We only rate limit the LLM part to prevent expensive calls.
_RATE_LIMIT_STORE: Dict[str, float] = {}
RATE_LIMIT_SECONDS = 5.0


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    response = await call_next(request)
    # Required for Godot 4 HTML5 export (SharedArrayBuffer)
    # response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return response

# ---------- Pydantic Models ----------

class ORUParseRequest(BaseModel):
    hl7_text: str
    use_llm: bool = True
    persist: bool = True


class PatientOut(BaseModel):
    id: str
    first_name: str
    last_name: str
    dob: str
    sex: str


class ObservationOut(BaseModel):
    code: str
    display: str
    value: Any
    unit: str
    reference_low: Optional[str] = None
    reference_high: Optional[str] = None
    flag: str = ""
    observation_datetime: str = ""
    status: str = ""
    source: str = "HL7"
    alert_level: str = ""
    alert_message: str = ""


class ORUParseResponse(BaseModel):
    patient: PatientOut
    clinical_summary: str
    structured_observations: List[ObservationOut]
    fhir_bundle: Dict[str, Any]
    hl7_ack: str = ""
    ai_analysis: Optional[Dict[str, Any]] = None


class SaveMessageRequest(BaseModel):
    patient: PatientOut
    clinical_summary: str
    structured_observations: List[ObservationOut]
    fhir_bundle: Dict[str, Any]
    raw_hl7: str


class MessageListItem(BaseModel):
    id: int
    timestamp: str
    patient_id: str
    first_name: str
    last_name: str
    dob: str
    sex: str


class MessageListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: List[MessageListItem]


class MessageDetailResponse(BaseModel):
    id: int
    timestamp: str
    raw_hl7: str
    patient: PatientOut
    fhir_bundle: Dict[str, Any]


class ObservationListResponse(BaseModel):
    message_id: int
    items: List[ObservationOut]


class QueryRequest(BaseModel):
    question: str
    history: List[Dict[str, str]] = []
    reasoning_depth: str = "standard"


class QueryResponse(BaseModel):
    success: bool
    answer: str
    highlights: List[str] = []
    sql_used: str = ""
    row_count: int = 0
    sources: List[Dict[str, Any]] = []  # RAG sources
    error: Optional[str] = None
    # New agent fields (backward compatible)
    reasoning_trace: List[Dict[str, Any]] = []
    tools_used: List[str] = []
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    clarification_options: List[str] = []


# Patient Timeline Models
class PatientListItem(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    dob: str
    sex: str
    visit_count: int
    last_visit: str


class PatientListResponse(BaseModel):
    total: int
    patients: List[PatientListItem]


class VisitObservation(BaseModel):
    code: str
    display: str
    value: Any
    unit: str
    reference_low: Optional[str] = None
    reference_high: Optional[str] = None
    flag: str = ""
    observation_datetime: str = ""
    status: str = ""
    alert_level: str = ""
    alert_message: str = ""


class PatientVisit(BaseModel):
    message_id: int
    date: str
    observations: List[VisitObservation]


class PatientTimelineResponse(BaseModel):
    patient: PatientOut
    visits: List[PatientVisit]
    visit_count: int


class PatientSummaryResponse(BaseModel):
    patient_id: str
    summary: str


# ---------- DB Helpers ----------

from .db import get_connection as _conn

# def _conn() -> sqlite3.Connection:
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     return conn


def _parse_fhir_bundle(raw_json: Optional[str]) -> Dict[str, Any]:
    if not raw_json:
        return {"resourceType": "Bundle", "type": "collection", "entry": []}
    try:
        obj = json.loads(raw_json)
        return obj if isinstance(obj, dict) else {"resourceType": "Bundle", "type": "collection", "entry": [], "_raw": raw_json}
    except Exception:
        return {"resourceType": "Bundle", "type": "collection", "entry": [], "_raw": raw_json}


def _obs_value(row: sqlite3.Row) -> Any:
    # Prefer numeric if present; fallback to raw string; else empty
    vnum = row["value_num"]
    if vnum is not None:
        return float(vnum)
    vraw = row["value_raw"]
    return vraw if vraw is not None else ""


# ---------- Routes ----------

from fastapi import Request
from datetime import datetime

@app.on_event("startup")
async def startup_event():
    # Prune old messages on startup
    from .db import prune_messages
    try:
        deleted = prune_messages(days_to_keep=2)
        if deleted > 0:
            print(f"Pruned {deleted} old messages on startup.")
    except Exception as e:
        print(f"Startup pruning failed: {e}")


@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
def query_assistant_endpoint(req: QueryRequest, request: Request) -> QueryResponse:
    """
    Natural language query endpoint using AI Agent.
    Agent decides which tools to use (database, guidelines, calculators, etc.)
    Falls back to legacy system on error.
    """
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    now_ts = __import__("time").time()
    last_ts = _RATE_LIMIT_STORE.get(client_ip, 0.0)
    
    if now_ts - last_ts < RATE_LIMIT_SECONDS:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few seconds.")
    
    _RATE_LIMIT_STORE[client_ip] = now_ts
    
    # Security: Block prompt injection at API layer
    from .security import detect_injection_patterns
    injection_warnings = detect_injection_patterns(req.question)
    if injection_warnings:
        print(f"SECURITY API BLOCK: {injection_warnings}")
        return QueryResponse(
            success=False,
            answer="Your query was blocked due to potentially unsafe content. Please ask a normal question about patient data.",
            error="Query blocked by input sanitization"
        )
    
    # Use new Agent system
    try:
        from .healthcare_agent import run_agent_query
        result = run_agent_query(req.question, req.history, depth=req.reasoning_depth)
        
        # If agent failed with an error, try legacy fallback
        if not result.get("success", False) and result.get("error"):
            print(f"Agent returned error, trying legacy: {result.get('error')}")
            raise Exception(result.get("error"))
        
        return QueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", "Sorry, I couldn't process that."),
            highlights=result.get("highlights", []),
            sql_used=result.get("sql_used", ""),
            row_count=result.get("row_count", 0),
            sources=result.get("sources", []),
            error=result.get("error"),
            reasoning_trace=result.get("reasoning_trace", []),
            tools_used=result.get("tools_used", []),
            needs_clarification=result.get("needs_clarification", False),
            clarification_question=result.get("clarification_question"),
            clarification_options=result.get("clarification_options", [])
        )
    except Exception as e:
        # Fallback to legacy system
        print(f"Agent error, falling back to legacy: {e}")
        from .query_assistant import process_query
        sanitized_q = sanitize_text(req.question)
        result = process_query(sanitized_q, req.history)
        
        return QueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", "Sorry, I couldn't process that."),
            highlights=result.get("highlights", []),
            sql_used=result.get("sql_used", ""),
            row_count=result.get("row_count", 0),
            sources=result.get("sources", []),
            error=result.get("error")
        )
    

# ---------- RAG Routes ----------

@app.get("/api/document/{filename}")
def get_document_content(filename: str, request: Request):
    """
    Get full text content of a RAG document.
    """
    # 1. Rate Limiting (Simple)
    client_ip = request.client.host if request.client else "unknown"
    now_ts = __import__("time").time()
    # Use a separate key prefix for internal docs to avoid blocking chat
    limit_key = f"doc_{client_ip}"
    last_ts = _RATE_LIMIT_STORE.get(limit_key, 0.0)
    
    if now_ts - last_ts < 0.5: # 0.5s limit to prevent scraping
        raise HTTPException(status_code=429, detail="Too many requests.")
    
    _RATE_LIMIT_STORE[limit_key] = now_ts

    # 2. Filename Validation (Strict Regex)
    import re
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")
    
    # 3. Extension Whitelist
    ALLOWED_EXTENSIONS = {'.txt', '.md', '.pdf', '.json', '.csv'}
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")
    
    # 4. Path Traversal Prevention (Strict)
    try:
        docs_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "docs"))
        file_path = os.path.abspath(os.path.join(docs_dir, filename))
        
        # Ensure the resolved path starts with the docs directory
        if not file_path.startswith(docs_dir):
            raise HTTPException(status_code=403, detail="Access denied")
            
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Document not found")
        
        # 5. Size Limit (e.g. 5MB) to prevent DOS
        if os.path.getsize(file_path) > 5 * 1024 * 1024:
             raise HTTPException(status_code=400, detail="Document too large")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filename": filename, "content": content}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error reading doc {filename}: {e}")
        raise HTTPException(status_code=500, detail="Error reading document")
    



# ---------- Patient Timeline Routes ----------

@app.get("/patients", response_model=PatientListResponse)
def list_patients() -> PatientListResponse:
    """
    Get list of unique patients with visit counts.
    """
    from .patient_timeline import get_unique_patients
    
    patients = get_unique_patients()
    items = [
        PatientListItem(
            patient_id=p["patient_id"],
            first_name=p["first_name"],
            last_name=p["last_name"],
            dob=p["dob"],
            sex=p["sex"],
            visit_count=p["visit_count"],
            last_visit=p["last_visit"],
        )
        for p in patients
    ]
    
    return PatientListResponse(total=len(items), patients=items)


@app.get("/patients/{patient_id}/timeline", response_model=PatientTimelineResponse)
def get_patient_timeline_endpoint(patient_id: str) -> PatientTimelineResponse:
    """
    Get full timeline for a patient including all visits and observations.
    """
    from .patient_timeline import get_patient_timeline
    
    timeline = get_patient_timeline(patient_id)
    
    if not timeline:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient = PatientOut(
        id=timeline["patient"]["patient_id"],
        first_name=timeline["patient"]["first_name"],
        last_name=timeline["patient"]["last_name"],
        dob=timeline["patient"]["dob"],
        sex=timeline["patient"]["sex"],
    )
    
    visits = []
    for v in timeline["visits"]:
        obs = [
            VisitObservation(
                code=o["code"],
                display=o["display"],
                value=o["value"],
                unit=o["unit"],
                reference_low=o.get("reference_low"),
                reference_high=o.get("reference_high"),
                flag=o.get("flag", ""),
                observation_datetime=o.get("observation_datetime", ""),
                status=o.get("status", ""),
                alert_level=o.get("alert_level", ""),
                alert_message=o.get("alert_message", ""),
            )
            for o in v["observations"]
        ]
        visits.append(PatientVisit(
            message_id=v["message_id"],
            date=v["date"],
            observations=obs,
        ))
    
    return PatientTimelineResponse(
        patient=patient,
        visits=visits,
        visit_count=timeline["visit_count"],
    )


@app.get("/patients/{patient_id}/summary", response_model=PatientSummaryResponse)
def get_patient_summary_endpoint(patient_id: str, request: Request) -> PatientSummaryResponse:
    """
    Get AI-generated journey summary for a patient.
    """
    from .patient_timeline import get_patient_timeline, generate_journey_summary
    
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    now_ts = __import__("time").time()
    last_ts = _RATE_LIMIT_STORE.get(client_ip, 0.0)
    
    if now_ts - last_ts < RATE_LIMIT_SECONDS:
        raise HTTPException(status_code=429, detail="Too many requests. Please wait a few seconds.")
    
    _RATE_LIMIT_STORE[client_ip] = now_ts
    
    timeline = get_patient_timeline(patient_id)
    
    if not timeline:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    summary = generate_journey_summary(timeline)
    
    return PatientSummaryResponse(patient_id=patient_id, summary=summary)



class ResetRequest(BaseModel):
    password: str

@app.delete("/messages", status_code=204)
def clear_all_messages_endpoint(req: ResetRequest):
    """
    Reset database to original sample data.
    Requires password validation.
    """
    from .db import delete_all_messages
    from .seed import seed_database
    
    # HARDCODED PASSWORD FOR DEMO (In production, use env vars)
    VALID_PASSWORDS = ["admin123", "demo-reset", "admin"]
    
    if req.password not in VALID_PASSWORDS:
        print(f"SECURITY: Failed reset attempt with password '{req.password}'")
        raise HTTPException(status_code=401, detail="Invalid admin password")

    try:
        # 1. Wipe everything
        delete_all_messages()
        
        # 2. Re-seed default data
        seed_database(verbose=False)
        return
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reset database: {e}")


@app.post("/messages", status_code=201)
def save_message_endpoint(req: SaveMessageRequest):
    """
    Save a fully verified message (patient + obs) to the DB.
    """
    from .db import insert_message_and_observations, init_db
    from .hl7_msh import parse_msh

    try:
        init_db()
        msh_obj = parse_msh(req.raw_hl7)
        msh_dict = msh_obj.__dict__ if msh_obj else {}

        insert_message_and_observations(
            received_at=str(datetime.utcnow()),
            raw_hl7=req.raw_hl7,
            patient=req.patient.dict(),
            observations=[o.dict() for o in req.structured_observations],
            fhir_bundle=req.fhir_bundle,
            msh=msh_dict,
        )
        return {"status": "saved"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save message: {e}")


@app.post("/oru/parse", response_model=ORUParseResponse)
async def parse_oru_endpoint(req: ORUParseRequest, request: Request) -> ORUParseResponse:
    """
    Run the ORU pipeline and return the result.
    If persist=False, it's a dry-run (preview).
    """
    # 0. Sanitize input (Strip emojis, non-standard unicode, injection tags)
    req.hl7_text = sanitize_text(req.hl7_text, strict_ascii=True)

    # 1. Basic Validation
    if not req.hl7_text or "MSH" not in req.hl7_text:
        raise HTTPException(status_code=400, detail="Invalid HL7 message. Must start with MSH segment.")

    # 1. Message Type Validation
    from .hl7_msh import parse_msh, build_ack
    msh = parse_msh(req.hl7_text)
    
    ack_message = ""
    if msh:
        # Generate positive ACK early
        ack_message = build_ack(msh, ack_code="AA", text="Message Received")
        
        # Check MSH-9 (Message Type). Should contain ORU (e.g. ORU^R01)
        if "ORU" not in (msh.message_type or "").upper():
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid Message Type: Expected ORU (Observation Result), received '{msh.message_type}'."
            )

    import asyncio
    try:
        # Rate limit check if requesting LLM
        if req.use_llm:
            print(f"DEBUG: API /oru/parse called. persist={req.persist}, use_llm={req.use_llm}", flush=True)
            client_ip = request.client.host if request.client else "unknown"
            now_ts = __import__("time").time()
            last_ts = _RATE_LIMIT_STORE.get(client_ip, 0.0)
            
            if now_ts - last_ts < RATE_LIMIT_SECONDS:
                raise HTTPException(status_code=429, detail="Too many AI requests. Please wait a few seconds.")
    
            _RATE_LIMIT_STORE[client_ip] = now_ts
    
        # Run in separate thread to avoid blocking the event loop during Bedrock call
        result: Dict[str, Any] = await asyncio.to_thread(run_oru_pipeline, req.hl7_text, req.use_llm, req.persist)
    except HTTPException:
        raise
    except Exception as e:
        # Catch any parser errors (like hl7apy failures) and return 400 if it's a data issue
        if "Msh missing" in str(e) or "Invalid" in str(e):
             raise HTTPException(status_code=400, detail=f"Failed to parse HL7: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Processing Error: {str(e)}")

    patient_dict = result.get("patient", {}) or {}
    clinical_summary = result.get("clinical_summary", "") or ""
    structured_list = result.get("structured_observations", []) or []
    fhir_bundle = result.get("fhir_bundle", {}) or {}
    ai_analysis = result.get("ai_analysis", {}) or {}

    patient = PatientOut(
        id=patient_dict.get("id", "patient-1"),
        first_name=patient_dict.get("first_name", ""),
        last_name=patient_dict.get("last_name", ""),
        dob=patient_dict.get("dob", ""),
        sex=patient_dict.get("sex", ""),
    )

    observations: List[ObservationOut] = []
    for o in structured_list:
        observations.append(
            ObservationOut(
                code=o.get("code", ""),
                display=o.get("display", "") or o.get("code", ""),
                value=o.get("value"),
                unit=o.get("unit", ""),
                reference_low=o.get("reference_low"),
                reference_high=o.get("reference_high"),
                flag=o.get("flag", "") or "",
                observation_datetime=o.get("observation_datetime", "") or "",
                status=o.get("status", "") or "",
                source=o.get("source", "HL7"),
                alert_level=o.get("alert_level", "") or "",
                alert_message=o.get("alert_message", "") or "",
            )
        )

    if not isinstance(fhir_bundle, dict):
        fhir_bundle = {"resourceType": "Bundle", "type": "collection", "entry": [], "_raw": fhir_bundle}

    return ORUParseResponse(
        patient=patient,
        clinical_summary=clinical_summary,
        structured_observations=observations,
        fhir_bundle=fhir_bundle,
        hl7_ack=ack_message,
        ai_analysis=ai_analysis
    )


@app.get("/messages", response_model=MessageListResponse)
def list_messages(
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> MessageListResponse:
    """
    List ingested HL7 messages from SQLite.
    """
    conn = _conn()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM hl7_messages").fetchone()["c"]

        rows = conn.execute(
            """
            SELECT
              id,
              received_at,
              patient_id,
              patient_first_name,
              patient_last_name,
              patient_dob,
              patient_sex
            FROM hl7_messages
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

        items: List[MessageListItem] = []
        for r in rows:
            items.append(
                MessageListItem(
                    id=int(r["id"]),
                    timestamp=str(r["received_at"] or ""),
                    patient_id=str(r["patient_id"] or ""),
                    first_name=str(r["patient_first_name"] or ""),
                    last_name=str(r["patient_last_name"] or ""),
                    dob=str(r["patient_dob"] or ""),
                    sex=str(r["patient_sex"] or ""),
                )
            )

        return MessageListResponse(total=int(total), limit=limit, offset=offset, items=items)
    finally:
        conn.close()


@app.get("/messages/{message_id}", response_model=MessageDetailResponse)
def get_message(message_id: int) -> MessageDetailResponse:
    """
    Get a single message + patient + fhir bundle.
    """
    conn = _conn()
    try:
        r = conn.execute(
            """
            SELECT
              id,
              received_at,
              raw_hl7,
              patient_id,
              patient_first_name,
              patient_last_name,
              patient_dob,
              patient_sex,
              fhir_bundle_json
            FROM hl7_messages
            WHERE id = ?
            """,
            (message_id,),
        ).fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Message not found")

        patient = PatientOut(
            id=str(r["patient_id"] or "patient-1"),
            first_name=str(r["patient_first_name"] or ""),
            last_name=str(r["patient_last_name"] or ""),
            dob=str(r["patient_dob"] or ""),
            sex=str(r["patient_sex"] or ""),
        )

        bundle = _parse_fhir_bundle(r["fhir_bundle_json"])

        return MessageDetailResponse(
            id=int(r["id"]),
            timestamp=str(r["received_at"] or ""),
            raw_hl7=str(r["raw_hl7"] or ""),
            patient=patient,
            fhir_bundle=bundle,
        )
    finally:
        conn.close()


@app.get("/messages/{message_id}/observations", response_model=ObservationListResponse)
def list_message_observations(message_id: int) -> ObservationListResponse:
    """
    Get observations for a message.
    """
    conn = _conn()
    try:
        exists = conn.execute("SELECT 1 FROM hl7_messages WHERE id = ?", (message_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Message not found")

        rows = conn.execute(
            """
            SELECT
              code,
              display,
              value_num,
              value_raw,
              unit,
              reference_low,
              reference_high,
              flag,
              observation_datetime,
              status,
              alert_level,
              alert_message
            FROM observations
            WHERE message_id = ?
            ORDER BY id ASC
            """,
            (message_id,),
        ).fetchall()

        items: List[ObservationOut] = []
        for r in rows:
            # Handle potential missing columns if DB wasn't fully migrated (safeguard)
            try:
                alert_lvl = str(r["alert_level"] or "")
                alert_msg = str(r["alert_message"] or "")
            except Exception:
                alert_lvl = ""
                alert_msg = ""

            items.append(
                ObservationOut(
                    code=str(r["code"] or ""),
                    display=str(r["display"] or r["code"] or ""),
                    value=_obs_value(r),
                    unit=str(r["unit"] or ""),
                    reference_low=r["reference_low"],
                    reference_high=r["reference_high"],
                    flag=str(r["flag"] or ""),
                    observation_datetime=str(r["observation_datetime"] or ""),
                    status=str(r["status"] or ""),
                    alert_level=alert_lvl,
                    alert_message=alert_msg,
                )
            )

        return ObservationListResponse(message_id=message_id, items=items)
    finally:
        conn.close()


# Must come last to avoid overriding API routes
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve index.html at root
@app.get("/")
async def read_index():
    return FileResponse('web/index.html')

# Liveness check (no DB access)
@app.get("/ping")
async def ping():
    return {"status": "ok"}

# Serve dashboard.html
@app.get("/dashboard.html")
async def read_dashboard():
    return FileResponse('web/dashboard.html')

# Serve patient.html
@app.get("/patient.html")
async def read_patient():
    return FileResponse('web/patient.html')


# ---------- Admin Routes ----------

# Global lock for reset operation
import asyncio
from asyncio import Lock
reset_lock = Lock()

import os
import time
from pydantic import BaseModel

class ResetRequest(BaseModel):
    password: str

@app.post("/admin/reset")
async def reset_demo_data(req: ResetRequest):
    """
    Reset database to initial demo state.
    Deletes all messages and reseeds with sample data.
    Requires password.
    """
    # Load password from env, default to d3m0th1s
    admin_password = os.getenv("ADMIN_PASSWORD", "d3m0th1s")

    if req.password != admin_password:
        # Anti-brute force delay
        time.sleep(1.0)
        raise HTTPException(status_code=401, detail="Incorrect Password")

    if reset_lock.locked():
        raise HTTPException(status_code=409, detail="Reset already in progress. Please wait.")

    async with reset_lock:
        try:
            # Run blocking operations in a threadpool to keep the server responsive
            loop = asyncio.get_running_loop()
            
            def _perform_reset():
                from .seed import seed_database
                # delete_all_messages() is called inside seed_database
                seed_database(verbose=False)
                
            await loop.run_in_executor(None, _perform_reset)
            
            return {"success": True, "message": "Database reset with 100 realistic patients and corresponding clinical data."}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")

# Mount the web directory for static assets (css, js)
app.mount("/", StaticFiles(directory="web"), name="static")

