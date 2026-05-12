import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db
from app.warden import Warden, WardenPolicy


def _seed_phi_db(db_path):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO hl7_messages (
                received_at, raw_hl7, patient_id, patient_first_name,
                patient_last_name, patient_dob, patient_sex, fhir_bundle_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-05-12 12:00:00",
                "MSH|^~\\&|TEST|",
                "P12345",
                "Sarah",
                "Jenkins",
                "1975-03-14",
                "F",
                "{}",
            ),
        )
        conn.execute(
            """
            INSERT INTO visits (
                visit_id, patient_id, visit_date, visit_type,
                provider_name, chief_complaint
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("V1", "P12345", "2026-05-12", "office", "Dr. Alice Chen", "follow up"),
        )
        conn.commit()
    finally:
        conn.close()


def _isolated_warden(tmp_path):
    db_path = str(tmp_path / "warden.db")
    audit_path = str(tmp_path / "warden_audit.jsonl")
    _seed_phi_db(db_path)
    warden = Warden(db_path=db_path)
    warden.policy.audit_log.log_path = audit_path
    return warden, audit_path


def _read_audit(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_warden_tokenizes_phi_with_temp_db(tmp_path):
    warden, _ = _isolated_warden(tmp_path)

    with warden.request_scope() as ctx:
        safe = ctx.anonymize(
            "Show Sarah Jenkins, P12345, born 1975-03-14, seen by Dr. Alice Chen"
        )

        assert "Sarah Jenkins" not in safe
        assert "P12345" not in safe
        assert "1975-03-14" not in safe
        assert "Dr. Alice Chen" not in safe
        assert "<<PAT_1>>" in safe
        assert "<<PID_1>>" in safe
        assert "<<PROV_1>>" in safe


def test_warden_deanonymizes_within_request_and_clears_after_scope(tmp_path):
    warden, _ = _isolated_warden(tmp_path)
    token_map_ref = None

    with warden.request_scope() as ctx:
        token_map_ref = ctx.token_map
        safe = ctx.anonymize("Sarah Jenkins")
        assert safe == "<<PAT_1>>"
        assert ctx.deanonymize(safe) == "Sarah Jenkins"
        assert token_map_ref.field_count > 0

    assert token_map_ref.field_count == 0


def test_warden_policy_audit_is_phi_free_for_allow_and_deny(tmp_path):
    warden, audit_path = _isolated_warden(tmp_path)

    with warden.request_scope() as ctx:
        allow = ctx.intercept("query_database", {"query": "show labs for <<PAT_1>>"})
        deny = ctx.intercept("query_database", {"query": "show contacts table"})

    assert allow.action == "ALLOW"
    assert deny.action == "DENY"

    audit_text = open(audit_path, "r", encoding="utf-8").read()
    assert "Sarah Jenkins" not in audit_text
    assert "P12345" not in audit_text
    assert "1975-03-14" not in audit_text
    assert "Dr. Alice Chen" not in audit_text

    entries = _read_audit(audit_path)
    assert [entry["decision"] for entry in entries] == ["ALLOW", "DENY"]
    assert entries[0]["phi_fields_anonymized"] > 0
    assert "patient_name" in entries[0]["field_types"]


def test_warden_unknown_tool_fails_closed_and_audits(tmp_path):
    warden, audit_path = _isolated_warden(tmp_path)

    with warden.request_scope() as ctx:
        decision = ctx.intercept("unknown_tool", {"query": "anything"})

    assert decision.action == "DENY"
    entries = _read_audit(audit_path)
    assert entries[-1]["tool"] == "unknown_tool"
    assert entries[-1]["decision"] == "DENY"


def test_warden_audit_write_failure_does_not_block_decision(tmp_path):
    warden, _ = _isolated_warden(tmp_path)
    warden.policy.audit_log.log_path = str(tmp_path / "missing" / "audit.jsonl")

    with warden.request_scope() as ctx:
        decision = ctx.intercept("query_database", {"query": "show labs"})

    assert decision.action == "ALLOW"


def test_warden_policy_schema_and_calculator_rules_without_db():
    policy = WardenPolicy()

    bad_schema = policy.intercept("query_database", {"query": 123})
    bad_calc = policy.intercept("clinical_calculator", {"calculation": "meld", "values": {}})
    good_calc = policy.intercept("clinical_calculator", {"calculation": "bmi", "values": {}})

    assert bad_schema.action == "DENY"
    assert bad_calc.action == "DENY"
    assert good_calc.action == "ALLOW"
