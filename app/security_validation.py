from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import Request, Response


SECURITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "ttl": {
        "demo_session_hours": int(os.getenv("SECURITY_DEMO_SESSION_HOURS", "12")),
        "hl7_parse_minutes": int(os.getenv("SECURITY_HL7_PARSE_MINUTES", "10")),
        "conversation_minutes": int(os.getenv("SECURITY_CONVERSATION_MINUTES", "30")),
    },
    "timeouts": {
        "llm_seconds": int(os.getenv("SECURITY_LLM_TIMEOUT_SECONDS", "60")),
        "sql_seconds": int(os.getenv("SECURITY_SQL_TIMEOUT_SECONDS", "10")),
        "hl7_parse_seconds": int(os.getenv("SECURITY_HL7_PARSE_TIMEOUT_SECONDS", "20")),
        "rag_seconds": int(os.getenv("SECURITY_RAG_TIMEOUT_SECONDS", "10")),
        "request_seconds": int(os.getenv("SECURITY_REQUEST_TIMEOUT_SECONDS", "90")),
    },
    "compatibility": {
        "allow_legacy_messages": os.getenv("SECURITY_ALLOW_LEGACY_MESSAGES", "false").lower() == "true",
        "allow_oru_direct_persist": os.getenv("SECURITY_ALLOW_ORU_DIRECT_PERSIST", "false").lower() == "true",
    },
    "deployment": {
        "mode": os.getenv("SECURITY_DEPLOYMENT_MODE", "demo"),
    },
}


AUDIT_BLOCKED_KEYS = {
    "raw_text",
    "raw_hl7",
    "question",
    "history",
    "answer",
    "token_map",
    "token_real_pairs",
    "patient_name",
    "patient_id",
    "patient_first_name",
    "patient_last_name",
    "dob",
    "patient_dob",
    "fhir_bundle",
    "fhir_bundle_json",
    "sql",
}


@dataclass(frozen=True)
class CanonicalInput:
    raw_present: bool
    normalized: str
    input_kind: str
    language: str = "en"
    decoded_payload_summaries: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    taint_labels: List[str] = field(default_factory=list)
    reject_reason: Optional[str] = None


@dataclass(frozen=True)
class IntentGrant:
    intent: str
    risk: str
    session_id: str
    request_id: str
    scope: str
    subject: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=list)
    allowed_tables: List[str] = field(default_factory=list)
    allowed_columns: Dict[str, List[str]] = field(default_factory=dict)
    output_fields: List[str] = field(default_factory=list)
    max_rows: int = 50
    expires_at: str = ""


@dataclass(frozen=True)
class SecurityDecision:
    action: str
    reason: str
    guard_name: str
    evidence_categories: List[str] = field(default_factory=list)
    audit_safe_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SafeConversationState:
    conversation_id: str
    session_id: str
    patient_ids: List[str] = field(default_factory=list)
    topic_codes: List[str] = field(default_factory=list)
    result_ids: List[str] = field(default_factory=list)
    scope: str = "none"
    intent: str = "none"
    expires_at: str = ""


@dataclass(frozen=True)
class TokenRecord:
    request_id: str
    token: str
    field_type: str
    source: str
    output_authorized: bool


@dataclass(frozen=True)
class Hl7ParseSession:
    parse_id: str
    session_id: str
    raw_hl7_hash: str
    status: str
    parse_result: Dict[str, Any]
    note_policy_result: Dict[str, Any]
    expires_at: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


def iso_after(**kwargs: int) -> str:
    return (utc_now() + timedelta(**kwargs)).isoformat()


def new_request_id() -> str:
    return f"req_{secrets.token_urlsafe(18)}"


def new_session_id() -> str:
    return f"sess_{secrets.token_urlsafe(24)}"


def new_parse_id() -> str:
    return f"parse_{secrets.token_urlsafe(24)}"


def hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="replace")).hexdigest()


def canonicalize_text(raw: Optional[str], input_kind: str) -> CanonicalInput:
    value = raw or ""
    normalized = value.replace("\x00", "").strip()
    warnings: List[str] = []
    if value != normalized:
        warnings.append("normalized_whitespace_or_nulls")
    return CanonicalInput(
        raw_present=bool(raw),
        normalized=normalized,
        input_kind=input_kind,
        warnings=warnings,
        taint_labels=["user_input"],
    )


def audit_safe_payload(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in (payload or {}).items():
        if key in AUDIT_BLOCKED_KEYS:
            safe[f"{key}_redacted"] = True
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, list):
            safe[key] = [item for item in value if isinstance(item, (str, int, float, bool))][:20]
        elif isinstance(value, dict):
            safe[key] = audit_safe_payload(value)
        else:
            safe[key] = str(type(value).__name__)
    return safe


def emit_governance_event(
    *,
    request_id: str,
    session_id: str,
    component: str,
    action: str,
    reason_code: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    from .db import insert_governance_event

    insert_governance_event(
        request_id=request_id,
        session_id=session_id,
        component=component,
        action=action,
        reason_code=reason_code,
        payload_json=json.dumps(audit_safe_payload(payload), sort_keys=True),
        created_at=iso_now(),
    )


def get_or_create_demo_session(request: Request, response: Optional[Response] = None) -> str:
    from .db import get_demo_session, upsert_demo_session

    supplied = request.cookies.get("demo_session_id") or request.headers.get("X-Session-Id")
    session_id = supplied if supplied and get_demo_session(supplied) else new_session_id()
    expires_at = iso_after(hours=SECURITY_CONFIG["ttl"]["demo_session_hours"])
    upsert_demo_session(session_id=session_id, expires_at=expires_at, last_seen_at=iso_now())
    if response is not None:
        response.set_cookie(
            key="demo_session_id",
            value=session_id,
            httponly=True,
            samesite="lax",
            max_age=SECURITY_CONFIG["ttl"]["demo_session_hours"] * 3600,
        )
    return session_id


def serialize_dataclass(obj: Any) -> Dict[str, Any]:
    return asdict(obj)
