import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.security_validation import IntentGrant, iso_after
from app.sql_guard import SqlGuard, require_safe_sql, validate_sql_select


def grant(**overrides):
    values = {
        "intent": "query",
        "risk": "low",
        "session_id": "sess_test",
        "request_id": "req_test",
        "scope": "demo",
        "allowed_tools": ["query_database"],
        "allowed_tables": ["hl7_messages", "observations", "visits", "medications", "diagnoses"],
        "allowed_columns": {},
        "output_fields": [],
        "max_rows": 10,
        "expires_at": iso_after(minutes=5),
    }
    values.update(overrides)
    return IntentGrant(**values)


def assert_denied(sql, reason_fragment, test_grant=None):
    result = validate_sql_select(sql, test_grant or grant())
    assert result.allowed is False
    assert reason_fragment.lower() in result.reason.lower()


def test_allows_basic_select_and_injects_limit():
    result = validate_sql_select(
        "SELECT patient_id, patient_first_name FROM hl7_messages ORDER BY received_at DESC",
        grant(),
    )

    assert result.allowed is True
    assert result.sql.endswith("LIMIT 10")
    assert result.limit_was_injected is True
    assert result.tables == ["hl7_messages"]
    assert result.columns["hl7_messages"] == ["patient_first_name", "patient_id", "received_at"]


def test_caps_existing_limit_to_grant_max_rows():
    result = validate_sql_select("SELECT patient_id FROM hl7_messages LIMIT 50", grant(max_rows=7))

    assert result.allowed is True
    assert result.sql == "SELECT patient_id FROM hl7_messages LIMIT 7"
    assert result.limit_was_capped is True


def test_preserves_limit_under_cap():
    result = validate_sql_select("SELECT patient_id FROM hl7_messages LIMIT 3", grant(max_rows=10))

    assert result.allowed is True
    assert result.sql == "SELECT patient_id FROM hl7_messages LIMIT 3"
    assert result.limit_was_injected is False
    assert result.limit_was_capped is False


def test_rejects_comments_semicolons_and_multiple_selects():
    assert_denied("SELECT patient_id FROM hl7_messages -- hide", "comments")
    assert_denied("SELECT patient_id FROM hl7_messages; SELECT patient_id FROM hl7_messages", "semicolon")
    assert_denied(
        "SELECT patient_id FROM hl7_messages WHERE id IN (SELECT message_id FROM observations)",
        "exactly one SELECT",
    )


@pytest.mark.parametrize(
    "sql, keyword",
    [
        ("PRAGMA table_info(hl7_messages)", "select"),
        ("SELECT patient_id FROM hl7_messages ATTACH DATABASE 'x' AS x", "ATTACH"),
        ("SELECT patient_id FROM hl7_messages WHERE id IN (DELETE FROM observations)", "DELETE"),
        ("SELECT patient_id FROM hl7_messages UNION SELECT patient_id FROM hl7_messages", "SELECT"),
    ],
)
def test_rejects_control_and_mutation_keywords(sql, keyword):
    assert_denied(sql, keyword)


def test_rejects_blocked_contacts_table_even_if_granted():
    test_grant = grant(allowed_tables=["hl7_messages", "contacts"])

    assert_denied("SELECT email FROM contacts LIMIT 5", "blocked table", test_grant)


def test_rejects_unknown_or_not_granted_table():
    assert_denied("SELECT id FROM sqlite_master LIMIT 1", "unknown table")
    assert_denied(
        "SELECT code FROM observations LIMIT 1",
        "table not allowed",
        grant(allowed_tables=["hl7_messages"]),
    )


def test_rejects_unsafe_functions_and_allows_safe_functions():
    assert_denied("SELECT load_extension('x') FROM hl7_messages", "function not allowed")

    result = validate_sql_select("SELECT COUNT(*) AS total FROM hl7_messages", grant())

    assert result.allowed is True
    assert result.sql.endswith("LIMIT 10")


def test_enforces_column_allowlist():
    test_grant = grant(
        allowed_tables=["hl7_messages"],
        allowed_columns={"hl7_messages": ["patient_id", "patient_first_name"]},
    )

    allowed = validate_sql_select("SELECT patient_id, patient_first_name FROM hl7_messages", test_grant)
    denied = validate_sql_select("SELECT patient_last_name FROM hl7_messages", test_grant)

    assert allowed.allowed is True
    assert denied.allowed is False
    assert "column not allowed" in denied.reason.lower()


def test_rejects_static_sensitive_columns():
    assert_denied("SELECT raw_hl7 FROM hl7_messages LIMIT 5", "unknown or non-allowlisted column")
    assert_denied("SELECT fhir_bundle_json FROM hl7_messages LIMIT 5", "unknown or non-allowlisted column")


def test_validates_join_aliases_and_qualified_columns():
    result = validate_sql_select(
        """
        SELECT h.patient_first_name, o.display, o.value_num
        FROM hl7_messages h
        JOIN observations o ON o.message_id = h.id
        WHERE UPPER(o.display) LIKE '%GLUCOSE%'
        ORDER BY o.value_num DESC
        """,
        grant(max_rows=5),
    )

    assert result.allowed is True
    assert result.sql.strip().endswith("LIMIT 5")
    assert result.tables == ["hl7_messages", "observations"]
    assert result.columns["hl7_messages"] == ["id", "patient_first_name"]
    assert result.columns["observations"] == ["display", "message_id", "value_num"]


def test_rejects_wildcards_and_ambiguous_unqualified_columns():
    assert_denied("SELECT * FROM hl7_messages LIMIT 5", "wildcard")
    assert_denied(
        "SELECT id FROM hl7_messages JOIN observations ON observations.message_id = hl7_messages.id",
        "ambiguous",
    )


def test_rejects_non_numeric_or_comma_limits():
    assert_denied("SELECT patient_id FROM hl7_messages LIMIT ?", "numeric")
    assert_denied("SELECT patient_id FROM hl7_messages LIMIT 10, 20", "comma-form")


def test_require_safe_sql_raises_on_denial():
    with pytest.raises(ValueError, match="blocked table"):
        require_safe_sql("SELECT email FROM contacts", grant(allowed_tables=["contacts"]))


def test_custom_guard_schema_can_be_used_for_lead_integration():
    guard = SqlGuard(schema={"safe_table": {"id", "name"}}, blocked_tables=set())
    test_grant = grant(allowed_tables=["safe_table"], allowed_columns={"safe_table": ["id"]})

    result = guard.validate("SELECT id FROM safe_table", test_grant)

    assert result.allowed is True
    assert result.sql == "SELECT id FROM safe_table LIMIT 10"
