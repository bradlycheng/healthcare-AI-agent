# app/api.py

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional

from .agent import run_oru_pipeline

import os
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
# AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
# AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "healthcare2025")

app = FastAPI(title="Healthcare HL7 → FHIR Agent API")

# Simple in-memory rate limiter: keys=IP, values=timestamp of last LLM request
# We only rate limit the LLM part to prevent expensive calls.
_RATE_LIMIT_STORE: Dict[str, float] = {}
RATE_LIMIT_SECONDS = 5.0


# ---------- Pydantic Models ----------

class ORUParseRequest(BaseModel):
    hl7_text: str
    use_llm: bool = True


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


class ORUParseResponse(BaseModel):
    patient: PatientOut
    clinical_summary: str
    structured_observations: List[ObservationOut]
    fhir_bundle: Dict[str, Any]


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


# ---------- DB Helpers ----------

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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

@app.get("/health")
def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/oru/parse", response_model=ORUParseResponse)
def parse_oru_endpoint(req: ORUParseRequest, request: Request) -> ORUParseResponse:
    """
    Run the ORU pipeline and return the result.

    Note: run_oru_pipeline() should also persist to SQLite if your agent does that.
    """
    # Rate limit check if requesting LLM
    if req.use_llm:
        client_ip = request.client.host if request.client else "unknown"
        now_ts = __import__("time").time()
        last_ts = _RATE_LIMIT_STORE.get(client_ip, 0.0)
        
        if now_ts - last_ts < RATE_LIMIT_SECONDS:
            # Too many requests - fallback to NO LLM to be nice, 
            # or could raise 429. Let's just disable LLM for this run so it's fast.
            # req.use_llm = False
            # Actually, per user request, let's strict limit it or raise exception.
            # But making it just disable LLM is a better UX for a demo so it doesn't crash.
            # Let's raise 429 so the UI knows to tell them "Slow down".
            raise HTTPException(status_code=429, detail="Too many AI requests. Please wait a few seconds.")

        _RATE_LIMIT_STORE[client_ip] = now_ts

    result: Dict[str, Any] = run_oru_pipeline(req.hl7_text, use_llm=req.use_llm)

    patient_dict = result.get("patient", {}) or {}
    clinical_summary = result.get("clinical_summary", "") or ""
    structured_list = result.get("structured_observations", []) or []
    fhir_bundle = result.get("fhir_bundle", {}) or {}

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
            )
        )

    if not isinstance(fhir_bundle, dict):
        fhir_bundle = {"resourceType": "Bundle", "type": "collection", "entry": [], "_raw": fhir_bundle}

    return ORUParseResponse(
        patient=patient,
        clinical_summary=clinical_summary,
        structured_observations=observations,
        fhir_bundle=fhir_bundle,
    )


@app.get("/messages", response_model=MessageListResponse)
def list_messages(
    limit: int = Query(50, ge=1, le=200),
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
              status
            FROM observations
            WHERE message_id = ?
            ORDER BY id ASC
            """,
            (message_id,),
        ).fetchall()

        items: List[ObservationOut] = []
        for r in rows:
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

# Serve dashboard.html
@app.get("/dashboard.html")
async def read_dashboard():
    return FileResponse('web/dashboard.html')

# Mount the web directory for static assets (css, js)
app.mount("/", StaticFiles(directory="web"), name="static")

