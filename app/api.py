# app/api.py

from __future__ import annotations

import json
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import datetime
from typing import Any, Dict, List, Optional

from .agent import run_oru_pipeline
from .security import sanitize_text

import sys
# Force unbuffered stdout
sys.stdout.reconfigure(encoding='utf-8')

import os
from fastapi import FastAPI, HTTPException, Query, Request, Response
from dotenv import load_dotenv

# Load environment variables from .env file (if present)
load_dotenv()
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .security_validation import (
    SECURITY_CONFIG,
    emit_governance_event,
    get_or_create_demo_session,
    hash_text,
    iso_after,
    new_parse_id,
    new_request_id,
)
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
_AGENT_EXECUTOR = ThreadPoolExecutor(max_workers=4)


@app.on_event("shutdown")
def shutdown_agent_executor():
    _AGENT_EXECUTOR.shutdown(wait=False, cancel_futures=True)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    response = await call_next(request)
    # Required for Godot 4 HTML5 export (SharedArrayBuffer)
    # response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    # response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
    return response
    
@app.on_event("startup")
def on_startup():
    from .db import cleanup_expired_security_state, init_db
    init_db()
    cleanup_expired_security_state()
    print("DEBUG: Database initialized", flush=True)

# ---------- Pydantic Models ----------

class ORUParseRequest(BaseModel):
    hl7_text: str
    use_llm: bool = True
    persist: bool = False


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
    parse_id: Optional[str] = None


class SaveMessageRequest(BaseModel):
    parse_id: Optional[str] = None
    patient: Optional[PatientOut] = None
    clinical_summary: Optional[str] = None
    structured_observations: List[ObservationOut] = []
    fhir_bundle: Dict[str, Any] = {}
    raw_hl7: str = ""


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


class ContactRequest(BaseModel):
    email: str
    nickname: Optional[str] = None # Honeypot field (should be empty)


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
    if vraw is not None and _is_note_like_observation(row) and not _debug_flag("show_protected_output"):
        return "[REDACTED_NOTE_TEXT]"
    return vraw if vraw is not None else ""


def _is_note_like_observation(row: sqlite3.Row) -> bool:
    code = str(row["code"] or "").lower()
    display = str(row["display"] or "").lower()
    return code == "note" or "note" in display or "clinical text" in display


def _audit_read_endpoint(
    request: Request,
    response: Response,
    *,
    component: str,
    reason_code: str,
    payload: Optional[Dict[str, Any]] = None,
) -> str:
    request_id = new_request_id()
    session_id = get_or_create_demo_session(request, response)
    emit_governance_event(
        request_id=request_id,
        session_id=session_id,
        component=component,
        action="ALLOW",
        reason_code=reason_code,
        payload=payload or {},
    )
    return request_id


def _debug_flag(name: str) -> bool:
    return bool(SECURITY_CONFIG.get("debug", {}).get(name, False))


def _run_agent_with_timeout(func, *args, timeout_seconds: int, **kwargs):
    future = _AGENT_EXECUTOR.submit(func, *args, **kwargs)
    return future.result(timeout=max(0.001, float(timeout_seconds)))


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


@app.post("/api/contact", status_code=201)
def contact_endpoint(req: ContactRequest, request: Request):
    """
    Save a contact request (email) to the database.
    Rate limited to prevent abuse.
    """
    # 0. Honeypot Check (Spam Protection)
    if req.nickname:
        # Silently fail (pretend it worked to confuse bots) or 400
        # Returning 201 keeps them guessing, but for now let's just return.
        print(f"SPAM BLOCK: Honeypot filled by {request.client.host}")
        return {"status": "received", "message": "Thanks!"}

    # 1. Input Validation
    if not req.email or "@" not in req.email or "." not in req.email:
        raise HTTPException(status_code=400, detail="Invalid email address.")

    # 2. Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    now_ts = __import__("time").time()
    limit_key = f"contact_{client_ip}"
    last_ts = _RATE_LIMIT_STORE.get(limit_key, 0.0)
    
    # Strict rate limit: 1 request per minute per IP
    if now_ts - last_ts < 60.0:
        raise HTTPException(status_code=429, detail="Too many contact requests. Please wait a minute.")
    
    _RATE_LIMIT_STORE[limit_key] = now_ts

    # 3. Save to DB
    from .db import save_contact_request
    success = save_contact_request(req.email, client_ip)
    
    if not success:
        # likely due to overflow limit
        raise HTTPException(status_code=503, detail="Contact list is full. Please try again later.")
        
    return {"status": "received", "message": "Thanks for your interest! We've saved your request."}


@app.post("/api/query", response_model=QueryResponse)
def query_assistant_endpoint(req: QueryRequest, request: Request, response: Response) -> QueryResponse:
    """
    Natural language query endpoint using AI Agent.
    Agent decides which tools to use (database, guidelines, calculators, etc.)
    Falls back to legacy system on error.
    """
    request_id = new_request_id()
    session_id = get_or_create_demo_session(request, response)
    from .safe_memory import conversation_id_for_session, load_state
    conversation_id = conversation_id_for_session(session_id)
    prior_state = load_state(conversation_id, session_id)
    emit_governance_event(
        request_id=request_id,
        session_id=session_id,
        component="api.query",
        action="START",
        reason_code="query_received",
        payload={
            "reasoning_depth": req.reasoning_depth,
            "history_count": len(req.history or []),
            "safe_state_present": prior_state is not None,
        },
    )

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
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query",
            action="DENY",
            reason_code="input_sanitization_block",
            payload={"warnings": injection_warnings},
        )
        return QueryResponse(
            success=False,
            answer="Your query was blocked due to potentially unsafe content. Please ask a normal question about patient data.",
            error="Query blocked by input sanitization"
        )
    
    try:
        from .grant_builder import build_query_grant
        from .healthcare_agent import run_agent_query
        from .intent_classifier import IntentClassificationError, classify_query_intent
        from .reference_resolver import resolve_safe_references

        resolution = resolve_safe_references(req.question, prior_state)
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query.references",
            action="ALLOW" if resolution.allowed else ("CLARIFY" if resolution.needs_clarification else "DENY"),
            reason_code=resolution.reason_code,
            payload={
                "safe_state_present": prior_state is not None,
                "referenced_patient_count": resolution.referenced_patient_count,
                "resolved_subject_present": resolution.subject is not None,
            },
        )
        if resolution.action == "deny":
            return QueryResponse(
                success=False,
                answer="I can't use a prior answer to widen scope or expose identifiers. Please ask a bounded clinical question.",
                error="Reference denied by governance policy.",
            )
        if resolution.needs_clarification:
            return QueryResponse(
                success=True,
                answer="I need a little more detail before I can safely use that reference.",
                needs_clarification=True,
                clarification_question="Which patient or clinical scope do you mean?",
                clarification_options=["Specify a patient ID", "Ask a new bounded clinical question"],
            )
        governed_question = resolution.question

        try:
            classification = classify_query_intent(
                governed_question,
                safe_state_present=prior_state is not None,
            )
        except IntentClassificationError as e:
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.query.intent",
                action="DENY",
                reason_code=str(e),
                payload={},
            )
            return QueryResponse(
                success=False,
                answer="I could not classify that request safely. Please rephrase as a normal clinical question.",
                error="Intent classification failed closed.",
            )

        grant = build_query_grant(
            session_id=session_id,
            request_id=request_id,
            intent=classification.intent,
            scope=classification.scope,
            subject=resolution.subject,
            max_rows=50,
        )
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query.intent",
            action="DENY" if classification.deny or grant.risk == "deny" else "ALLOW",
            reason_code=classification.reason_code,
            payload={
                "intent": classification.intent,
                "scope": classification.scope,
                "risk": grant.risk,
                "allowed_tools": grant.allowed_tools,
            },
        )
        if classification.deny or grant.risk == "deny":
            return QueryResponse(
                success=False,
                answer="I can't perform that request. Please ask a normal read-only clinical question.",
                error="Request denied by governance policy.",
            )
        if classification.needs_clarification:
            return QueryResponse(
                success=True,
                answer="Could you clarify what clinical information you want me to look up?",
                needs_clarification=True,
                clarification_question="What clinical information should I use?",
                clarification_options=["Patient data", "Guideline reference", "Calculator"],
            )

        try:
            result = _run_agent_with_timeout(
                run_agent_query,
                governed_question,
                [],
                depth=req.reasoning_depth,
                grant=grant,
                timeout_seconds=SECURITY_CONFIG["timeouts"]["request_seconds"],
            )
        except FutureTimeoutError:
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.query",
                action="DENY",
                reason_code="query_timeout_no_memory_commit",
                payload={"timeout_seconds": SECURITY_CONFIG["timeouts"]["request_seconds"]},
            )
            return QueryResponse(
                success=False,
                answer="I could not process that request safely before the timeout.",
                error="Query timed out; no memory was committed.",
            )
        
        if not result.get("success", False) and result.get("error"):
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.query",
                action="DENY",
                reason_code="agent_failed_no_legacy_fallback",
                payload={"tools_used": result.get("tools_used", [])},
            )
            return QueryResponse(
                success=False,
                answer="I could not process that request safely.",
                error="Agent failed; legacy fallback is disabled by governance.",
            )
        
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query",
            action="ALLOW",
            reason_code="query_completed",
            payload={
                "tools_used": result.get("tools_used", []),
                "row_count": result.get("row_count", 0),
                "source_count": len(result.get("sources", []) or []),
                "token_restore_summary": (result.get("safe_metadata") or {}).get("token_restore_summary", {}),
            },
        )
        from .safe_memory import commit_successful_turn
        memory_committed = commit_successful_turn(
            conversation_id=conversation_id,
            session_id=session_id,
            agent_result=result,
        )
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query.memory",
            action="ALLOW" if memory_committed else "SKIP",
            reason_code="safe_memory_commit" if memory_committed else "safe_memory_not_committed",
            payload={"committed": memory_committed},
        )
        return QueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", "Sorry, I couldn't process that."),
            highlights=result.get("highlights", []),
            sql_used=result.get("sql_used", "") if _debug_flag("show_sql_used") else "",
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
        print(f"Agent error, legacy fallback disabled: {e}")
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.query",
            action="DENY",
            reason_code="agent_exception_no_legacy_fallback",
            payload={"error_type": type(e).__name__},
        )
        return QueryResponse(
            success=False,
            answer="I could not process that request safely.",
            error="Agent error; legacy fallback is disabled by governance.",
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
def list_patients(request: Request, response: Response) -> PatientListResponse:
    """
    Get list of unique patients with visit counts.
    """
    from .patient_timeline import get_unique_patients
    
    patients = get_unique_patients()
    _audit_read_endpoint(
        request,
        response,
        component="api.patients",
        reason_code="patient_list_read",
        payload={"count": len(patients)},
    )
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
def get_patient_timeline_endpoint(patient_id: str, request: Request, response: Response) -> PatientTimelineResponse:
    """
    Get full timeline for a patient including all visits and observations.
    """
    from .patient_timeline import get_patient_timeline
    
    timeline = get_patient_timeline(patient_id)
    
    if not timeline:
        raise HTTPException(status_code=404, detail="Patient not found")
    _audit_read_endpoint(
        request,
        response,
        component="api.patients.timeline",
        reason_code="patient_timeline_read",
        payload={"patient_id": patient_id, "visit_count": timeline["visit_count"]},
    )
    
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
def get_patient_summary_endpoint(patient_id: str, request: Request, response: Response) -> PatientSummaryResponse:
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
    _audit_read_endpoint(
        request,
        response,
        component="api.patients.summary",
        reason_code="patient_summary_requested",
        payload={"patient_id": patient_id, "visit_count": timeline["visit_count"]},
    )
    
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
    
    # Require an environment variable to be explicitly set
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        print("SECURITY: Reset attempt blocked. ADMIN_PASSWORD is not configured.")
        raise HTTPException(status_code=403, detail="Reset functionality is disabled. ADMIN_PASSWORD is not configured.")

    if req.password != admin_password:
        import time
        time.sleep(1.0) # Anti-brute force delay
        print(f"SECURITY: Failed reset attempt. Invalid password.")
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
def save_message_endpoint(req: SaveMessageRequest, request: Request, response: Response):
    """
    Save a fully verified message (patient + obs) to the DB.
    """
    from .db import (
        claim_hl7_parse_session,
        insert_message_and_observations,
        init_db,
        mark_hl7_parse_session_persisted,
    )
    from .hl7_msh import parse_msh

    request_id = new_request_id()
    session_id = get_or_create_demo_session(request, response)
    try:
        init_db()
        if not req.parse_id:
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.messages",
                action="DENY",
                reason_code="missing_parse_id",
                payload={"legacy_compatibility": SECURITY_CONFIG["compatibility"]["allow_legacy_messages"]},
            )
            if not SECURITY_CONFIG["compatibility"]["allow_legacy_messages"]:
                raise HTTPException(
                    status_code=400,
                    detail="Saving requires a server-issued parse_id. Re-parse the HL7 message before saving.",
                )
            if req.patient is None:
                raise HTTPException(status_code=400, detail="Legacy save requires patient data.")
            msh_obj = parse_msh(req.raw_hl7)
            msh_dict = msh_obj.__dict__ if msh_obj else {}
            message_id = insert_message_and_observations(
                received_at=str(datetime.utcnow()),
                raw_hl7=req.raw_hl7,
                patient=req.patient.dict(),
                observations=[o.dict() for o in req.structured_observations],
                fhir_bundle=req.fhir_bundle,
                msh=msh_dict,
            )
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.messages",
                action="ALLOW",
                reason_code="legacy_message_saved_compatibility_mode",
                payload={"message_id": message_id, "observation_count": len(req.structured_observations)},
            )
            return {"status": "saved", "message_id": message_id}

        parse_row = claim_hl7_parse_session(req.parse_id, session_id)
        if parse_row is None:
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.messages",
                action="DENY",
                reason_code="invalid_or_expired_parse_id",
                payload={"parse_id": req.parse_id},
            )
            raise HTTPException(status_code=400, detail="Invalid or expired parse_id.")

        parse_result = json.loads(parse_row["parse_result_json"])
        raw_hl7 = parse_result.get("raw_hl7", "")
        patient_data = parse_result.get("patient", {}) or {}
        observations_data = parse_result.get("structured_observations", []) or []
        fhir_bundle = parse_result.get("fhir_bundle", {}) or {}

        msh_obj = parse_msh(raw_hl7)
        msh_dict = msh_obj.__dict__ if msh_obj else {}

        message_id = insert_message_and_observations(
            received_at=str(datetime.utcnow()),
            raw_hl7=raw_hl7,
            patient=patient_data,
            observations=observations_data,
            fhir_bundle=fhir_bundle,
            msh=msh_dict,
        )
        mark_hl7_parse_session_persisted(req.parse_id, session_id, message_id)
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.messages",
            action="ALLOW",
            reason_code="parse_session_persisted",
            payload={
                "parse_id": req.parse_id,
                "message_id": message_id,
                "observation_count": len(observations_data),
            },
        )
        return {"status": "saved", "message_id": message_id}
    except HTTPException:
        raise
    except Exception as e:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.messages",
            action="DENY",
            reason_code="message_save_exception",
            payload={"error_type": type(e).__name__},
        )
        raise HTTPException(status_code=500, detail="Failed to save message.")


@app.post("/oru/parse", response_model=ORUParseResponse)
async def parse_oru_endpoint(req: ORUParseRequest, request: Request, response: Response) -> ORUParseResponse:
    """
    Run the ORU pipeline and return the result.
    If persist=False, it's a dry-run (preview).
    """
    request_id = new_request_id()
    session_id = get_or_create_demo_session(request, response)
    emit_governance_event(
        request_id=request_id,
        session_id=session_id,
        component="api.oru_parse",
        action="START",
        reason_code="hl7_parse_received",
        payload={"persist": req.persist, "use_llm": req.use_llm, "raw_length": len(req.hl7_text or "")},
    )

    direct_persist_allowed = SECURITY_CONFIG["compatibility"]["allow_oru_direct_persist"]
    if req.persist and not direct_persist_allowed:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="DENY",
            reason_code="direct_oru_persist_disabled",
            payload={"legacy_compatibility": direct_persist_allowed},
        )
        raise HTTPException(
            status_code=400,
            detail="Direct ORU persistence is disabled. Parse with persist=false, then save using the server-issued parse_id.",
        )

    # 0. Sanitize input (Strip emojis, non-standard unicode, injection tags)
    req.hl7_text = sanitize_text(req.hl7_text, strict_ascii=True)

    from .hl7_guard import validate_hl7_message
    guard_result = validate_hl7_message(req.hl7_text)
    if not guard_result.ok:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="DENY",
            reason_code="hl7_guard_denied",
            payload={
                "errors": [issue.code for issue in guard_result.errors],
                "metadata": guard_result.metadata,
            },
        )
        raise HTTPException(status_code=400, detail="Invalid HL7 message.")

    # 1. Basic Validation
    if not req.hl7_text or "MSH" not in req.hl7_text:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="DENY",
            reason_code="missing_msh",
            payload={},
        )
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
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.oru_parse",
                action="DENY",
                reason_code="non_oru_message_type",
                payload={"message_type": msh.message_type},
            )
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
        result: Dict[str, Any] = await asyncio.wait_for(
            asyncio.to_thread(run_oru_pipeline, req.hl7_text, req.use_llm, req.persist),
            timeout=SECURITY_CONFIG["timeouts"]["hl7_parse_seconds"],
        )
    except asyncio.TimeoutError:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="DENY",
            reason_code="hl7_parse_timeout",
            payload={"timeout_seconds": SECURITY_CONFIG["timeouts"]["hl7_parse_seconds"]},
        )
        raise HTTPException(status_code=504, detail="HL7 parse timed out.")
    except HTTPException:
        raise
    except Exception as e:
        # Catch any parser errors (like hl7apy failures) and return 400 if it's a data issue
        if "Msh missing" in str(e) or "Invalid" in str(e):
            emit_governance_event(
                request_id=request_id,
                session_id=session_id,
                component="api.oru_parse",
                action="DENY",
                reason_code="hl7_parse_invalid",
                payload={"error_type": type(e).__name__},
            )
            raise HTTPException(status_code=400, detail="Failed to parse HL7.")
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="DENY",
            reason_code="hl7_parse_exception",
            payload={"error_type": type(e).__name__},
        )
        raise HTTPException(status_code=500, detail="Internal processing error.")

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

    parse_id: Optional[str] = None
    if not req.persist:
        from .db import create_hl7_parse_session

        parse_id = new_parse_id()
        parse_result = {
            "raw_hl7": req.hl7_text,
            "patient": patient.dict(),
            "clinical_summary": clinical_summary,
            "structured_observations": [o.dict() for o in observations],
            "fhir_bundle": fhir_bundle,
            "ai_analysis": ai_analysis,
        }
        create_hl7_parse_session(
            parse_id=parse_id,
            session_id=session_id,
            raw_hl7_hash=hash_text(req.hl7_text),
            parse_result=parse_result,
            note_policy_result={"status": "not_evaluated_phase_1"},
            expires_at=iso_after(minutes=SECURITY_CONFIG["ttl"]["hl7_parse_minutes"]),
        )
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="ALLOW",
            reason_code="parse_session_created",
            payload={"parse_id": parse_id, "observation_count": len(observations)},
        )
    else:
        emit_governance_event(
            request_id=request_id,
            session_id=session_id,
            component="api.oru_parse",
            action="ALLOW",
            reason_code="hl7_persisted_directly",
            payload={"message_id": result.get("id"), "observation_count": len(observations)},
        )

    return ORUParseResponse(
        patient=patient,
        clinical_summary=clinical_summary,
        structured_observations=observations,
        fhir_bundle=fhir_bundle,
        hl7_ack=ack_message,
        ai_analysis=ai_analysis,
        parse_id=parse_id,
    )


@app.get("/messages", response_model=MessageListResponse)
def list_messages(
    request: Request,
    response: Response,
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> MessageListResponse:
    """
    List ingested HL7 messages from SQLite.
    """
    conn = _conn()
    try:
        total = conn.execute("SELECT COUNT(*) AS c FROM hl7_messages").fetchone()["c"]
        _audit_read_endpoint(
            request,
            response,
            component="api.messages",
            reason_code="message_list_read",
            payload={"limit": limit, "offset": offset, "total": int(total)},
        )

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
def get_message(message_id: int, request: Request, response: Response) -> MessageDetailResponse:
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
        _audit_read_endpoint(
            request,
            response,
            component="api.messages",
            reason_code="message_detail_read",
            payload={"message_id": message_id},
        )

        patient = PatientOut(
            id=str(r["patient_id"] or "patient-1"),
            first_name=str(r["patient_first_name"] or ""),
            last_name=str(r["patient_last_name"] or ""),
            dob=str(r["patient_dob"] or ""),
            sex=str(r["patient_sex"] or ""),
        )

        protected_output = _debug_flag("show_protected_output")
        bundle = _parse_fhir_bundle(r["fhir_bundle_json"]) if protected_output else {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [],
            "redacted": True,
        }

        return MessageDetailResponse(
            id=int(r["id"]),
            timestamp=str(r["received_at"] or ""),
            raw_hl7=str(r["raw_hl7"] or "") if protected_output else "[REDACTED_PROTECTED_OUTPUT]",
            patient=patient,
            fhir_bundle=bundle,
        )
    finally:
        conn.close()


@app.get("/messages/{message_id}/observations", response_model=ObservationListResponse)
def list_message_observations(message_id: int, request: Request, response: Response) -> ObservationListResponse:
    """
    Get observations for a message.
    """
    conn = _conn()
    try:
        exists = conn.execute("SELECT 1 FROM hl7_messages WHERE id = ?", (message_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Message not found")
        _audit_read_endpoint(
            request,
            response,
            component="api.messages.observations",
            reason_code="message_observations_read",
            payload={"message_id": message_id},
        )

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
    # Load password from env, requires explicit configuration
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        print("SECURITY: Reset attempt blocked. ADMIN_PASSWORD is not configured.")
        raise HTTPException(status_code=403, detail="Reset functionality is disabled. ADMIN_PASSWORD is not configured.")

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

# ---------- Contact and Lead Gen ----------

class ContactRequest(BaseModel):
    email: str
    nickname: Optional[str] = None # Honeypot

@app.post("/api/contact")
async def handle_contact(req: ContactRequest, request: Request):
    """
    Handle contact form submissions.
    Includes a honeypot field 'nickname' which must be empty.
    """
    # 1. Honeypot check
    if req.nickname:
        print(f"Honeypot triggered by IP {request.client.host}")
        # Return success to fool bot, but don't save
        return {"status": "received"}

    # 2. Rate Limit (Simple IP-based)
    client_ip = request.client.host
    now = time.time()
    last_request = _RATE_LIMIT_STORE.get(client_ip, 0)
    
    if now - last_request < 60.0: # 1 minute cooldown for contacts
        raise HTTPException(status_code=429, detail="Please wait a minute before sending another request.")
    
    _RATE_LIMIT_STORE[client_ip] = now

    # 3. Save to DB
    from .db import get_connection
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO contacts (email, ip_address, created_at) VALUES (?, ?, ?)",
            (req.email, client_ip, datetime.now().isoformat())
        )
        conn.commit()
        print(f"New contact saved: {req.email}")
        return {"status": "saved"}
    except Exception as e:
        print(f"Error saving contact: {e}")
        raise HTTPException(status_code=500, detail="Failed to save contact information.")
    finally:
        conn.close()

# Mount the web directory for static assets (css, js)
app.mount("/", StaticFiles(directory="web"), name="static")

