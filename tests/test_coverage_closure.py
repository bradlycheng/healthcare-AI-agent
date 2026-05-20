import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


VALID_ORU = "\r".join(
    [
        "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG1|P|2.5",
        "PID|1||PREAD||Reader^Pat||19800101|F",
        "OBR|1||ORD1|BMP^Basic Metabolic Panel",
        "OBX|1|NM|2345-7^Glucose||120|mg/dL|70-110|H|||F",
    ]
)


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
    serialized = json.dumps(events, default=str)
    forbidden = [
        "Reader",
        "Pat",
        "19800101",
        "MSH|",
        "FHIR",
        "Bundle",
        "Traceback",
        "token_map",
        "token_real_pairs",
    ]
    for value in forbidden:
        assert value not in serialized


def test_document_endpoint_emits_phi_free_allow_and_deny_audit():
    import app.api as api

    _clear_governance_events()
    api._RATE_LIMIT_STORE.clear()
    client = TestClient(api.app)

    allowed = client.get("/api/document/glucose_guidelines.txt")
    api._RATE_LIMIT_STORE.clear()
    denied = client.get("/api/document/unsafe.exe")

    assert allowed.status_code == 200
    assert denied.status_code == 400
    events = _governance_events()
    reason_codes = {event["reason_code"] for event in events}
    assert "document_read" in reason_codes
    assert "document_extension_denied" in reason_codes
    _assert_events_phi_free(events)


def test_admin_reset_disabled_bad_password_and_success_are_audited(monkeypatch):
    import app.api as api
    import app.seed as seed

    _clear_governance_events()
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    monkeypatch.setattr(api.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(seed, "seed_database", lambda verbose=False: None)

    client = TestClient(api.app)
    disabled = client.post("/admin/reset", json={"password": "wrong"})

    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    bad = client.post("/admin/reset", json={"password": "wrong"})
    ok = client.post("/admin/reset", json={"password": "secret"})

    assert disabled.status_code == 403
    assert bad.status_code == 401
    assert ok.status_code == 200
    reason_codes = {event["reason_code"] for event in _governance_events()}
    assert "admin_password_not_configured" in reason_codes
    assert "admin_password_invalid" in reason_codes
    assert "admin_reset_completed" in reason_codes


def test_delete_messages_admin_path_audits_without_raw_payload(monkeypatch):
    import app.api as api
    import app.db as db
    import app.seed as seed

    _clear_governance_events()
    monkeypatch.setenv("ADMIN_PASSWORD", "secret")
    monkeypatch.setattr(api.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(db, "delete_all_messages", lambda: None)
    monkeypatch.setattr(seed, "seed_database", lambda verbose=False: None)

    client = TestClient(api.app)
    bad = client.request("DELETE", "/messages", json={"password": "wrong"})
    ok = client.request("DELETE", "/messages", json={"password": "secret"})

    assert bad.status_code == 401
    assert ok.status_code == 204
    events = _governance_events()
    reason_codes = {event["reason_code"] for event in events}
    assert "admin_password_invalid" in reason_codes
    assert "admin_messages_reset" in reason_codes
    assert "secret" not in json.dumps(events)


def test_phi_read_endpoints_emit_phi_free_audit(monkeypatch):
    import app.api as api
    import app.patient_timeline as patient_timeline
    from app.db import insert_message_and_observations

    _clear_governance_events()
    api._RATE_LIMIT_STORE.clear()
    monkeypatch.setattr(patient_timeline, "generate_journey_summary", lambda timeline: "Stable summary.")

    message_id = insert_message_and_observations(
        raw_hl7=VALID_ORU,
        patient={"id": "PREAD", "first_name": "Reader", "last_name": "Pat", "dob": "19800101", "sex": "F"},
        observations=[{"code": "2345-7", "display": "Glucose", "value": 120, "unit": "mg/dL", "status": "F"}],
        fhir_bundle={},
    )

    client = TestClient(api.app)
    responses = [
        client.get("/patients"),
        client.get("/messages"),
        client.get(f"/messages/{message_id}"),
        client.get(f"/messages/{message_id}/observations"),
        client.get("/patients/PREAD/timeline"),
    ]
    api._RATE_LIMIT_STORE.clear()
    responses.append(client.get("/patients/PREAD/summary"))

    assert all(response.status_code == 200 for response in responses)
    events = _governance_events()
    reason_codes = {event["reason_code"] for event in events}
    assert "patient_list_read" in reason_codes
    assert "message_list_read" in reason_codes
    assert "message_detail_read" in reason_codes
    assert "message_observations_read" in reason_codes
    assert "patient_timeline_read" in reason_codes
    assert "patient_summary_requested" in reason_codes
    _assert_events_phi_free(events)


def test_mllp_ingest_uses_hl7_guard_before_pipeline(monkeypatch):
    import app.mllp_server as mllp

    _clear_governance_events()
    captured = {"called": 0}

    def fake_pipeline(hl7):
        captured["called"] += 1
        return {"ok": True}

    monkeypatch.setattr(mllp, "run_oru_pipeline", fake_pipeline)

    mllp.process_mllp_hl7(VALID_ORU)

    invalid = "\r".join(
        [
            "MSH|^~\\&|LAB|HOSP|APP|FAC|202501010000||ORU^R01|MSG2|P|2.5",
            "PID|1||PREAD||Reader^Pat||19800101|F",
            "OBR|1||ORD1|BMP^Basic Metabolic Panel",
            "OBX|1|TX|NOTE^Narrative||DROP TABLE patients||||||F",
        ]
    )
    try:
        mllp.process_mllp_hl7(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid MLLP HL7 should fail before pipeline")

    assert captured["called"] == 1
    reason_codes = {event["reason_code"] for event in _governance_events()}
    assert "mllp_hl7_persisted" in reason_codes
    assert "hl7_guard_denied" in reason_codes
