import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.security_validation import IntentGrant, TokenRecord, iso_after
from app.token_guard import TOKEN_REDACTION, TokenGuard, restore_text


def _grant(*output_fields, session_id="sess_a", request_id="req_a"):
    return IntentGrant(
        intent="token_guard_test",
        risk="low",
        session_id=session_id,
        request_id=request_id,
        scope="test",
        output_fields=list(output_fields),
        expires_at=iso_after(minutes=5),
    )


def _expired_grant(*output_fields):
    return IntentGrant(
        intent="token_guard_test",
        risk="low",
        session_id="sess_a",
        request_id="req_a",
        scope="test",
        output_fields=list(output_fields),
        expires_at=iso_after(minutes=-1),
    )


def test_creates_opaque_phi_patient_token_and_restores_when_authorized():
    scope = TokenGuard().request_scope(_grant("patient_name"))

    record = scope.create_token("Jane Doe", field_type="patient_name")
    result = scope.restore_text(f"Patient {record.token} is stable.")

    assert record.token.startswith("<<PHI_PAT_")
    assert "Jane" not in record.token
    assert result.text == "Patient Jane Doe is stable."
    assert result.restored_count == 1
    assert result.redacted_count == 0


def test_redacts_guessed_token_without_request_record():
    scope = TokenGuard().request_scope(_grant("patient_name"))

    result = scope.restore_text("Patient <<PHI_PAT_guess>> is stable.")

    assert result.text == f"Patient {TOKEN_REDACTION} is stable."
    assert result.redacted_tokens == ["<<PHI_PAT_guess>>"]


def test_redacts_stale_or_wrong_request_record():
    scope = TokenGuard().request_scope(_grant("patient_name", request_id="req_current"))
    stale = TokenRecord(
        request_id="req_old",
        token="<<PHI_PAT_stale>>",
        field_type="patient_name",
        source="server",
        output_authorized=True,
    )
    scope.import_record(stale, "Jane Doe")

    result = scope.restore_text("Patient <<PHI_PAT_stale>> is stable.")

    assert result.text == f"Patient {TOKEN_REDACTION} is stable."


def test_redacts_wrong_session_restore_attempt():
    scope = TokenGuard().request_scope(_grant("patient_name", session_id="sess_owner"))
    record = scope.create_token("Jane Doe", field_type="patient_name")

    result = scope.restore_text(record.token, session_id="sess_attacker")

    assert result.text == TOKEN_REDACTION


def test_redacts_user_or_rag_injected_tokens_even_if_registered():
    scope = TokenGuard().request_scope(_grant("patient_name"))
    user_record = scope.create_token("Jane Doe", field_type="patient_name", source="user")
    rag_record = scope.create_token("Patient 123", field_type="patient_id", source="rag")

    result = scope.restore_text(f"{user_record.token} {rag_record.token}")

    assert result.text == f"{TOKEN_REDACTION} {TOKEN_REDACTION}"
    assert result.redacted_count == 2


def test_redacts_output_authorized_false_token():
    scope = TokenGuard().request_scope(_grant("patient_name"))
    record = scope.create_token(
        "Jane Doe",
        field_type="patient_name",
        output_authorized=False,
    )

    result = scope.restore_text(record.token)

    assert result.text == TOKEN_REDACTION


def test_redacts_field_type_not_authorized_by_grant():
    scope = TokenGuard().request_scope(_grant("patient_name"))
    record = scope.create_token("1980-01-01", field_type="patient_dob")

    result = scope.restore_text(f"DOB {record.token}")

    assert result.text == f"DOB {TOKEN_REDACTION}"


def test_redacts_when_grant_is_expired():
    scope = TokenGuard().request_scope(_expired_grant("patient_name"))
    record = scope.create_token("Jane Doe", field_type="patient_name")

    result = scope.restore_text(record.token)

    assert result.text == TOKEN_REDACTION


def test_metadata_only_helper_does_not_restore_real_values():
    grant = _grant("patient_name")
    record = TokenRecord(
        request_id=grant.request_id,
        token="<<PHI_PAT_metadata>>",
        field_type="patient_name",
        source="server",
        output_authorized=True,
    )

    result = restore_text(record.token, records=[record], grant=grant)

    assert result.text == TOKEN_REDACTION


def test_audit_summary_excludes_real_values():
    scope = TokenGuard().request_scope(_grant("patient_name", "patient_id"))
    scope.create_token("Jane Doe", field_type="patient_name")
    scope.create_token("P123", field_type="patient_id")

    summary = scope.audit_summary()

    assert summary.token_count == 2
    assert summary.field_types == ["patient_id", "patient_name"]
    assert "Jane Doe" not in repr(summary)
    assert "P123" not in repr(summary)
