import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VALID_ORU = "\r".join(
    [
        "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5",
        "PID|1||PTEST||Doe^Jane||19800101|F",
        "OBR|1||ORD1|BMP^Basic Metabolic Panel",
        "OBX|1|NM|2345-7^Glucose||120|mg/dL|70-110|H|||F",
    ]
)


def _fake_oru_result():
    return {
        "patient": {
            "id": "PTEST",
            "first_name": "Jane",
            "last_name": "Doe",
            "dob": "19800101",
            "sex": "F",
        },
        "clinical_summary": "Glucose high.",
        "structured_observations": [
            {
                "code": "2345-7",
                "display": "Glucose",
                "value": 120,
                "unit": "mg/dL",
                "reference_low": "70",
                "reference_high": "110",
                "flag": "H",
                "status": "F",
                "source": "HL7",
            }
        ],
        "fhir_bundle": {"resourceType": "Bundle", "type": "collection", "entry": []},
        "ai_analysis": {},
    }


def _clear_governance_events():
    from app.db import get_connection, init_db

    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM governance_events")
        conn.commit()
    finally:
        conn.close()


def _governance_events():
    from app.db import get_connection, init_db

    init_db()
    conn = get_connection()
    try:
        return [
            dict(row)
            for row in conn.execute(
                "SELECT component, action, reason_code, payload_json FROM governance_events ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()


def _assert_events_phi_free(events):
    forbidden = [
        "Jane",
        "Doe",
        "19800101",
        "MSH|",
        "FHIR",
        "Bundle",
        "token_map",
        "token_real_pairs",
        "Traceback",
    ]
    serialized = json.dumps(events, default=str)
    for value in forbidden:
        assert value not in serialized


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    import app.api as api

    api._RATE_LIMIT_STORE.clear()


def test_parse_preview_persist_replay_and_tamper_ignored(monkeypatch):
    import app.api as api
    from app.db import get_connection

    _clear_governance_events()
    monkeypatch.setattr(api, "run_oru_pipeline", lambda hl7_text, use_llm, persist: _fake_oru_result())

    client = TestClient(api.app)
    parse_response = client.post("/oru/parse", json={"hl7_text": VALID_ORU, "use_llm": False, "persist": False})

    assert parse_response.status_code == 200
    parse_id = parse_response.json()["parse_id"]
    assert parse_id

    save_response = client.post(
        "/messages",
        json={
            "parse_id": parse_id,
            "patient": {"id": "EVIL", "first_name": "Mallory", "last_name": "Injected", "dob": "19000101", "sex": "M"},
            "structured_observations": [{"code": "EVIL", "display": "Tampered", "value": 999, "unit": "x"}],
            "fhir_bundle": {"resourceType": "Bundle", "entry": [{"resource": {"id": "evil"}}]},
            "clinical_summary": "tampered summary",
            "raw_hl7": "tampered",
        },
    )

    assert save_response.status_code == 201
    message_id = save_response.json()["message_id"]

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT patient_id, patient_first_name, patient_last_name, patient_dob, fhir_bundle_json FROM hl7_messages WHERE id = ?",
            (message_id,),
        ).fetchone()
        obs = conn.execute("SELECT code, display, value_num FROM observations WHERE message_id = ?", (message_id,)).fetchone()
    finally:
        conn.close()

    assert row["patient_id"] == "PTEST"
    assert row["patient_first_name"] == "Jane"
    assert row["patient_last_name"] == "Doe"
    assert row["patient_dob"] == "19800101"
    assert "evil" not in row["fhir_bundle_json"].lower()
    assert obs["code"] == "2345-7"
    assert obs["display"] == "Glucose"
    assert obs["value_num"] == 120

    replay_response = client.post("/messages", json={"parse_id": parse_id})
    assert replay_response.status_code == 400

    events = _governance_events()
    reason_codes = {event["reason_code"] for event in events}
    assert "parse_session_created" in reason_codes
    assert "parse_session_persisted" in reason_codes
    assert "invalid_or_expired_parse_id" in reason_codes
    _assert_events_phi_free(events)


def test_wrong_session_parse_id_fails(monkeypatch):
    import app.api as api

    _clear_governance_events()
    monkeypatch.setattr(api, "run_oru_pipeline", lambda hl7_text, use_llm, persist: _fake_oru_result())

    owner = TestClient(api.app)
    attacker = TestClient(api.app)

    parse_response = owner.post("/oru/parse", json={"hl7_text": VALID_ORU, "use_llm": False, "persist": False})
    assert parse_response.status_code == 200

    response = attacker.post("/messages", json={"parse_id": parse_response.json()["parse_id"]})

    assert response.status_code == 400
    assert "Invalid or expired" in response.json()["detail"]
    assert "invalid_or_expired_parse_id" in {event["reason_code"] for event in _governance_events()}


def test_missing_parse_id_and_hl7_guard_denial_are_audited():
    import app.api as api

    _clear_governance_events()
    client = TestClient(api.app)

    missing = client.post("/messages", json={})
    invalid_hl7 = client.post("/oru/parse", json={"hl7_text": "PID|1||P1", "use_llm": False})

    assert missing.status_code == 400
    assert invalid_hl7.status_code == 400

    events = _governance_events()
    reason_codes = {event["reason_code"] for event in events}
    assert "missing_parse_id" in reason_codes
    assert "hl7_guard_denied" in reason_codes
    _assert_events_phi_free(events)


def test_classifier_failure_does_not_call_agent(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api as api
    import app.healthcare_agent as healthcare_agent
    import app.intent_classifier as intent_classifier
    from app.intent_classifier import IntentClassificationError

    _clear_governance_events()

    def fail_classifier(question, *, safe_state_present=False):
        raise IntentClassificationError("intent_classifier_unknown_intent")

    def agent_should_not_run(*args, **kwargs):
        raise AssertionError("agent should not run after classifier failure")

    monkeypatch.setattr(intent_classifier, "classify_query_intent", fail_classifier)
    monkeypatch.setattr(healthcare_agent, "run_agent_query", agent_should_not_run)

    response = TestClient(api.app).post("/api/query", json={"question": "do something strange"})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "classification failed" in response.json()["error"].lower()
    assert "intent_classifier_unknown_intent" in {event["reason_code"] for event in _governance_events()}


def test_classifier_deny_does_not_call_agent(monkeypatch):
    from fastapi.testclient import TestClient

    import app.api as api
    import app.healthcare_agent as healthcare_agent
    import app.intent_classifier as intent_classifier
    from app.intent_classifier import QueryIntentClassification

    _clear_governance_events()

    def deny_classifier(question, *, safe_state_present=False):
        return QueryIntentClassification(intent="export", scope="cohort", risk="deny", reason_code="deny_intent_export", deny=True)

    def agent_should_not_run(*args, **kwargs):
        raise AssertionError("agent should not run after denied intent")

    monkeypatch.setattr(intent_classifier, "classify_query_intent", deny_classifier)
    monkeypatch.setattr(healthcare_agent, "run_agent_query", agent_should_not_run)

    response = TestClient(api.app).post("/api/query", json={"question": "export all patient identifiers"})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "denied" in response.json()["error"].lower()
    assert "deny_intent_export" in {event["reason_code"] for event in _governance_events()}


def test_expired_parse_session_and_conversation_state_are_unusable():
    from app.db import claim_hl7_parse_session, create_hl7_parse_session, upsert_conversation_state
    from app.safe_memory import load_state
    from app.security_validation import iso_after

    create_hl7_parse_session(
        parse_id="parse_expired_endpoint_test",
        session_id="sess_expired_endpoint_test",
        raw_hl7_hash="hash",
        parse_result={"patient": {"id": "P1"}},
        note_policy_result={"status": "ok"},
        expires_at=iso_after(minutes=-1),
    )
    upsert_conversation_state(
        conversation_id="conv_expired_endpoint_test",
        session_id="sess_expired_endpoint_test",
        state={
            "conversation_id": "conv_expired_endpoint_test",
            "session_id": "sess_expired_endpoint_test",
            "patient_ids": ["P1"],
            "topic_codes": [],
            "result_ids": [],
            "scope": "cohort",
            "intent": "clinical_query",
            "expires_at": iso_after(minutes=-1),
        },
        expires_at=iso_after(minutes=-1),
    )

    assert claim_hl7_parse_session("parse_expired_endpoint_test", "sess_expired_endpoint_test") is None
    assert load_state("conv_expired_endpoint_test", "sess_expired_endpoint_test") is None
