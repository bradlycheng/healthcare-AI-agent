import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_low_level_llm_imports_only_in_gateway():
    violations = []
    for path in Path("app").glob("*.py"):
        if path.name in {"llm_client.py", "llm_gateway.py"}:
            continue
        text = path.read_text(encoding="utf-8")
        if "llm_client" in text or "call_llm(" in text or "call_llm_for_json(" in text:
            violations.append(str(path))
    assert violations == []


def test_governance_audit_payload_redacts_phi_keys():
    from app.security_validation import audit_safe_payload

    safe = audit_safe_payload(
        {
            "request_id": "req_test",
            "question": "Who is John Smith?",
            "raw_hl7": "MSH|...",
            "patient_id": "P123",
            "patient_name": "John Smith",
            "count": 3,
        }
    )

    assert safe["request_id"] == "req_test"
    assert safe["count"] == 3
    assert safe["question_redacted"] is True
    assert safe["raw_hl7_redacted"] is True
    assert safe["patient_id_redacted"] is True
    assert safe["patient_name_redacted"] is True
    assert "John Smith" not in str(safe)
    assert "P123" not in str(safe)


def test_warden_requires_grant_for_tool_execution():
    from app.warden import Warden

    warden = Warden()
    with warden.request_scope() as ctx:
        decision = ctx.intercept("query_database", {"query": "show patients"})

    assert decision.action == "DENY"
    assert "grant" in decision.reason.lower()


def test_warden_exact_schema_rejects_extra_fields():
    from app.security_validation import IntentGrant, iso_after
    from app.warden import Warden

    grant = IntentGrant(
        intent="test",
        risk="low",
        session_id="sess_test",
        request_id="req_test",
        scope="demo",
        allowed_tools=["query_database"],
        expires_at=iso_after(minutes=5),
    )

    warden = Warden()
    with warden.request_scope(grant=grant) as ctx:
        decision = ctx.intercept("query_database", {"query": "show patients", "role": "admin"})

    assert decision.action == "DENY"
    assert "unexpected" in decision.reason.lower()


def test_warden_rejects_expired_grant():
    from app.security_validation import IntentGrant, iso_after
    from app.warden import Warden

    grant = IntentGrant(
        intent="test",
        risk="low",
        session_id="sess_test",
        request_id="req_test",
        scope="demo",
        allowed_tools=["query_database"],
        expires_at=iso_after(minutes=-1),
    )

    warden = Warden()
    with warden.request_scope(grant=grant) as ctx:
        decision = ctx.intercept("query_database", {"query": "show patients"})

    assert decision.action == "DENY"
    assert "expired" in decision.reason.lower()


def test_messages_requires_parse_id_by_default():
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    response = client.post(
        "/messages",
        json={
            "raw_hl7": "MSH|^~\\&|A|B|C|D|202501010000||ORU^R01|1|P|2.5\rPID|1||P1||Doe^Jane",
            "patient": {"id": "P1", "first_name": "Jane", "last_name": "Doe", "dob": "", "sex": ""},
            "clinical_summary": "fake",
            "structured_observations": [],
            "fhir_bundle": {"resourceType": "Bundle"},
        },
    )

    assert response.status_code == 400
    assert "parse_id" in response.json()["detail"]


def test_oru_parse_rejects_direct_persist_by_default():
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    response = client.post(
        "/oru/parse",
        json={
            "persist": True,
            "use_llm": False,
            "hl7_text": "MSH|^~\\&|A|B|C|D|202501010000||ORU^R01|1|P|2.5\rPID|1||P1||Doe^Jane",
        },
    )

    assert response.status_code == 400
    assert "parse_id" in response.json()["detail"]


def test_hl7_parse_session_claim_is_one_time(tmp_path):
    from app.db import claim_hl7_parse_session, create_hl7_parse_session
    from app.security_validation import iso_after

    db_path = str(tmp_path / "agent.db")
    create_hl7_parse_session(
        parse_id="parse_test",
        session_id="sess_test",
        raw_hl7_hash="hash",
        parse_result={"patient": {"id": "P1"}},
        note_policy_result={"status": "ok"},
        expires_at=iso_after(minutes=5),
        db_path=db_path,
    )

    first = claim_hl7_parse_session("parse_test", "sess_test", db_path=db_path)
    second = claim_hl7_parse_session("parse_test", "sess_test", db_path=db_path)

    assert first is not None
    assert second is None
