import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_clinical_query_grant_has_sql_scope_and_phi_outputs():
    from app.grant_builder import build_query_grant

    grant = build_query_grant(session_id="sess_test", requested_tools=["query_database"])

    assert grant.allowed_tools == ["query_database"]
    assert "hl7_messages" in grant.allowed_tables
    assert "contacts" not in grant.allowed_tables
    assert "patient_id" in grant.output_fields
    assert grant.max_rows == 50


def test_guideline_intent_cannot_gain_database_tool():
    from app.grant_builder import build_query_grant

    grant = build_query_grant(
        session_id="sess_test",
        intent="guideline_reference",
        requested_tools=["query_database", "search_guidelines"],
    )

    assert grant.allowed_tools == ["search_guidelines"]
    assert grant.allowed_tables == []
    assert "patient_id" not in grant.output_fields


def test_deny_intent_gets_empty_grant():
    from app.grant_builder import build_query_grant

    grant = build_query_grant(session_id="sess_test", intent="export")

    assert grant.risk == "deny"
    assert grant.allowed_tools == []
    assert grant.output_fields == []
    assert grant.max_rows == 0


def test_narrow_to_tool_strips_non_sql_scope():
    from app.grant_builder import build_query_grant, narrow_to_tool

    grant = build_query_grant(session_id="sess_test")
    narrowed = narrow_to_tool(grant, "search_guidelines")

    assert narrowed.allowed_tools == ["search_guidelines"]
    assert narrowed.allowed_tables == []
    assert narrowed.allowed_columns == {}


def test_narrow_to_disallowed_tool_fails_closed():
    from app.grant_builder import build_query_grant, narrow_to_tool

    grant = build_query_grant(session_id="sess_test", intent="guideline_reference")
    narrowed = narrow_to_tool(grant, "query_database")

    assert narrowed.allowed_tools == []
    assert narrowed.max_rows == 0
