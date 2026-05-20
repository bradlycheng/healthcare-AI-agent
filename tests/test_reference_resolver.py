import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def state(**overrides):
    from app.security_validation import SafeConversationState, iso_after

    values = {
        "conversation_id": "conv_test",
        "session_id": "sess_test",
        "patient_ids": ["P1"],
        "topic_codes": [],
        "result_ids": [],
        "scope": "single_patient",
        "intent": "clinical_query",
        "expires_at": iso_after(minutes=30),
    }
    values.update(overrides)
    return SafeConversationState(**values)


def test_resolves_single_patient_pronoun_from_safe_state():
    from app.reference_resolver import resolve_safe_references

    result = resolve_safe_references("how are his labs?", state(patient_ids=["P123"]))

    assert result.action == "resolved"
    assert result.subject == "P123"
    assert "P123" not in result.question


def test_resolves_first_one_from_bounded_cohort_state():
    from app.reference_resolver import resolve_safe_references

    result = resolve_safe_references(
        "show the first one in more detail",
        state(patient_ids=["P1", "P2"], scope="cohort"),
    )

    assert result.action == "resolved"
    assert result.subject == "P1"


def test_ambiguous_reference_clarifies_instead_of_guessing():
    from app.reference_resolver import resolve_safe_references

    result = resolve_safe_references("what about his trend?", state(patient_ids=["P1", "P2"], scope="cohort"))

    assert result.needs_clarification is True
    assert result.reason_code == "ambiguous_reference"


def test_missing_state_reference_clarifies():
    from app.reference_resolver import resolve_safe_references

    result = resolve_safe_references("what about that patient?", None)

    assert result.needs_clarification is True
    assert result.reason_code == "reference_without_safe_state"


def test_reference_export_and_identifier_jumps_are_denied():
    from app.reference_resolver import resolve_safe_references

    export = resolve_safe_references("export those to csv", state(patient_ids=["P1", "P2"], scope="cohort"))
    identifiers = resolve_safe_references("give me those patient identifiers", state(patient_ids=["P1", "P2"], scope="cohort"))

    assert export.action == "deny"
    assert identifiers.action == "deny"


def test_single_patient_to_cohort_jump_clarifies():
    from app.reference_resolver import resolve_safe_references

    result = resolve_safe_references("now show all patients like this", state(patient_ids=["P1"], scope="single_patient"))

    assert result.needs_clarification is True
    assert result.reason_code == "scope_jump_single_patient_to_cohort"
