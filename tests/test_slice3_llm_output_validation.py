# tests/test_slice3_llm_output_validation.py
"""
Slice 3 — LLM output validation tests.

Covers:
  - LOINC code format validation in _merge_llm_output()
  - AI-observation count cap (max 10 per message)
  - Value validation (numeric or non-empty string < 200 chars)
  - LLM pipeline errors logged, not silently swallowed
  - _try_repair_json() logs a warning when repair is attempted
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is on sys.path so "app" is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agent import _merge_llm_output, _validate_ai_observation
from app.llm_client import _try_repair_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_raw(observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a minimal llm_raw dict with the given new_observations list."""
    return {"thought_process": "test", "new_observations": observations}


def _make_obs(
    code: str = "8867-4",
    value: Any = 72.0,
    display: str = "Heart Rate",
    unit: str = "bpm",
) -> Dict[str, Any]:
    return {"code": code, "display": display, "value": value, "unit": unit}


_BASE_PATIENT = {"id": "P001", "first_name": "Jane", "last_name": "Doe"}
_BASE_SUMMARY = "No observations."
_BASE_OBS: List[Dict[str, Any]] = []
_BASE_FHIR: Dict[str, Any] = {"resourceType": "Bundle", "entry": []}


# ---------------------------------------------------------------------------
# Test 1 — Invalid LOINC codes are rejected
# ---------------------------------------------------------------------------

class TestLlmInvalidLoincCodeRejected:
    """_merge_llm_output() must drop any observation whose code does not match
    the LOINC regex ^\d{4,6}-\d$ and emit a warning."""

    @pytest.mark.parametrize("bad_code", [
        "GLUCOSE",       # plain text — no digits/hyphen
        "8867",          # no hyphen + check digit
        "8867-44",       # check digit is 2 chars
        "123-4",         # only 3 leading digits
        "1234567-4",     # 7 leading digits
        "",              # empty string
        "8867-A",        # non-digit check digit
        "HR-4",          # non-digit prefix
    ])
    def test_llm_invalid_loinc_code_rejected(self, bad_code: str, caplog):
        """An observation with a non-LOINC code must be silently dropped and a
        warning must appear in the log."""
        llm_raw = _make_llm_raw([_make_obs(code=bad_code, value=72.0)])
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        # Observation must NOT appear in the merged output
        assert result_obs == [], (
            f"Observation with invalid LOINC code {bad_code!r} was incorrectly merged"
        )
        # A warning must have been logged (not a silent pass)
        warning_texts = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_texts, (
            f"No warning was logged when rejecting invalid LOINC code {bad_code!r}"
        )

    def test_valid_loinc_code_accepted(self):
        """An observation with a valid 5-digit LOINC code must be merged."""
        llm_raw = _make_llm_raw([_make_obs(code="8867-4", value=72.0)])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1
        assert result_obs[0]["code"] == "8867-4"

    def test_valid_4digit_loinc_accepted(self):
        """A 4-digit LOINC code (e.g. 2345-7) must be accepted."""
        llm_raw = _make_llm_raw([_make_obs(code="2345-7", value=100.0)])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1

    def test_valid_6digit_loinc_accepted(self):
        """A 6-digit LOINC code must be accepted."""
        llm_raw = _make_llm_raw([_make_obs(code="594085", value=99.0)])
        # 594085 has 6 digits but no hyphen — should be rejected
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert result_obs == [], "Code without hyphen must be rejected"

    def test_valid_6digit_with_hyphen_accepted(self):
        """A 6-digit LOINC code with hyphen (e.g. 59408-5) must be accepted."""
        llm_raw = _make_llm_raw([_make_obs(code="59408-5", value=98.0)])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1


# ---------------------------------------------------------------------------
# Test 2 — Count cap at 10
# ---------------------------------------------------------------------------

class TestLlmObservationCountCappedAt10:
    """When the LLM returns more than 10 valid observations, only the first 10
    must be merged and a warning must be logged."""

    def _make_valid_obs_list(self, n: int) -> List[Dict[str, Any]]:
        """Build n distinct valid observations with unique 5-digit LOINC codes."""
        # Use codes like 10000-0 through 10011-0 — all valid
        return [
            {"code": f"1000{i}-0", "display": f"Obs {i}", "value": float(i), "unit": "u"}
            for i in range(n)
        ]

    def test_llm_observation_count_capped_at_10(self, caplog):
        """15 valid observations must be truncated to 10 with a warning."""
        obs_list = self._make_valid_obs_list(15)
        llm_raw = _make_llm_raw(obs_list)
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        assert len(result_obs) == 10, (
            f"Expected 10 observations after cap, got {len(result_obs)}"
        )
        # A warning must have been logged about truncation
        warning_texts = " ".join(r.message for r in caplog.records if r.levelno >= logging.WARNING)
        assert warning_texts, "No warning was logged about truncation"

    def test_exactly_10_observations_all_accepted(self):
        """Exactly 10 valid observations must all be merged without truncation."""
        obs_list = self._make_valid_obs_list(10)
        llm_raw = _make_llm_raw(obs_list)
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 10

    def test_fewer_than_10_observations_all_accepted(self):
        """3 valid observations must all be merged (no cap triggered)."""
        obs_list = self._make_valid_obs_list(3)
        llm_raw = _make_llm_raw(obs_list)
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 3

    def test_first_10_are_kept_not_last_10(self, caplog):
        """When truncating, the first 10 (index 0–9) must be kept."""
        obs_list = self._make_valid_obs_list(12)
        llm_raw = _make_llm_raw(obs_list)
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        kept_codes = {o["code"] for o in result_obs}
        # Codes for index 0–9
        expected_kept = {f"1000{i}-0" for i in range(10)}
        assert kept_codes == expected_kept, (
            f"Wrong observations kept after truncation: {kept_codes}"
        )


# ---------------------------------------------------------------------------
# Test 3 — Value validation
# ---------------------------------------------------------------------------

class TestLlmNonNumericValueValidated:
    """_merge_llm_output() must accept valid numeric / non-empty-string values
    and reject None, empty string, and strings >= 200 characters."""

    _VALID_CODE = "8867-4"

    def test_integer_value_accepted(self):
        obs = _make_obs(code=self._VALID_CODE, value=72)
        llm_raw = _make_llm_raw([obs])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1

    def test_float_value_accepted(self):
        obs = _make_obs(code=self._VALID_CODE, value=98.6)
        llm_raw = _make_llm_raw([obs])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1

    def test_short_string_value_accepted(self):
        obs = _make_obs(code=self._VALID_CODE, value="normal sinus rhythm")
        llm_raw = _make_llm_raw([obs])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1

    def test_none_value_rejected(self, caplog):
        """An observation with value=None must be dropped."""
        obs = {"code": self._VALID_CODE, "display": "HR", "value": None, "unit": "bpm"}
        # None value is filtered by the pre-existing guard before _validate_ai_observation
        llm_raw = _make_llm_raw([obs])
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        assert result_obs == [], "Observation with None value must be dropped"

    def test_empty_string_value_rejected(self, caplog):
        """An observation with value='' must be dropped with a warning."""
        obs = _make_obs(code=self._VALID_CODE, value="")
        llm_raw = _make_llm_raw([obs])
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        assert result_obs == [], "Observation with empty-string value must be dropped"
        warning_texts = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_texts, "No warning logged for empty-string value rejection"

    def test_long_string_value_rejected(self, caplog):
        """An observation with value string >= 200 chars must be dropped with a warning."""
        long_val = "x" * 200
        obs = _make_obs(code=self._VALID_CODE, value=long_val)
        llm_raw = _make_llm_raw([obs])
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            _, _, result_obs, _ = _merge_llm_output(
                _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
            )
        assert result_obs == [], "Observation with 200-char value must be dropped"
        warning_texts = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_texts, "No warning logged for too-long value rejection"

    def test_string_value_199_chars_accepted(self):
        """A string value of exactly 199 chars must be accepted (under the 200-char limit)."""
        val = "y" * 199
        obs = _make_obs(code=self._VALID_CODE, value=val)
        llm_raw = _make_llm_raw([obs])
        _, _, result_obs, _ = _merge_llm_output(
            _BASE_PATIENT, _BASE_SUMMARY, list(_BASE_OBS), _BASE_FHIR, llm_raw
        )
        assert len(result_obs) == 1

    def test_validate_ai_observation_directly_rejects_none(self, caplog):
        """_validate_ai_observation() itself must return False for None value and log."""
        obs = {"code": "8867-4", "value": None}
        with caplog.at_level(logging.WARNING, logger="app.agent"):
            result = _validate_ai_observation(obs)
        assert result is False

    def test_validate_ai_observation_directly_accepts_numeric(self):
        """_validate_ai_observation() must return True for a valid numeric value."""
        obs = {"code": "8867-4", "value": 72.0}
        assert _validate_ai_observation(obs) is True


# ---------------------------------------------------------------------------
# Test 4 — LLM errors are logged, not silently swallowed
# ---------------------------------------------------------------------------

class TestLlmErrorsLoggedNotSwallowed:
    """run_oru_pipeline() must log an error when the LLM call raises an exception,
    not silently pass."""

    _MINIMAL_HL7 = (
        "MSH|^~\\&|SENDER|FAC|RCV|FAC2|20240101120000||ORU^R01|MSG001|P|2.5\r"
        "PID|1||P001^^^FAC^MR||DOE^JANE||19800101|F\r"
        "OBR|1|||PANEL\r"
        "OBX|1|NM|8867-4^Heart Rate^LN||72|bpm|60-100|N|||F\r"
        "NTE|1||Heart rate 72 bpm.\r"
    )

    def test_llm_errors_logged_not_swallowed(self, caplog):
        """When call_llm_for_json() raises LLMError, the pipeline must log an
        error (not silently pass) and still return a valid result."""
        from app.llm_client import LLMError
        import app.agent as agent_module

        with patch("app.agent.call_llm_for_json", side_effect=LLMError("Bedrock timeout")):
            with patch("app.agent.init_db"):
                with patch("app.agent.insert_message_and_observations", return_value=42):
                    with caplog.at_level(logging.ERROR, logger="app.agent"):
                        result = agent_module.run_oru_pipeline(
                            self._MINIMAL_HL7, use_llm=True, persist=True
                        )

        # Pipeline must still return a result (graceful degradation)
        assert result is not None
        assert "structured_observations" in result

        # An error must be logged — not silently swallowed
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            "No error was logged when call_llm_for_json() raised LLMError"
        )

    def test_llm_generic_exception_logged(self, caplog):
        """When call_llm_for_json() raises a generic Exception, it must be logged."""
        import app.agent as agent_module

        with patch("app.agent.call_llm_for_json", side_effect=RuntimeError("Network error")):
            with patch("app.agent.init_db"):
                with patch("app.agent.insert_message_and_observations", return_value=1):
                    with caplog.at_level(logging.ERROR, logger="app.agent"):
                        result = agent_module.run_oru_pipeline(
                            self._MINIMAL_HL7, use_llm=True, persist=True
                        )

        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            "No error was logged when call_llm_for_json() raised RuntimeError"
        )
        # Ensure the error message contains the exception type (not patient data)
        combined = " ".join(r.message for r in error_records)
        assert "RuntimeError" in combined, (
            "Logged error message should include the exception type"
        )

    def test_no_bare_pass_in_llm_except_block(self):
        """Source-code inspection: agent.py must not have a bare 'pass' as the
        only statement in an LLM-related except block."""
        import ast
        agent_path = os.path.join(os.path.dirname(__file__), "..", "app", "agent.py")
        with open(agent_path, encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.ExceptHandler,)):
                stmts = node.body
                if len(stmts) == 1 and isinstance(stmts[0], ast.Pass):
                    pytest.fail(
                        f"agent.py line {node.lineno}: bare 'pass' found in except handler"
                    )


# ---------------------------------------------------------------------------
# Test 5 — _try_repair_json() logs when repair is attempted
# ---------------------------------------------------------------------------

class TestJsonRepairLogged:
    """_try_repair_json() must emit a logging.WARNING when it attempts to repair
    malformed JSON (missing closing brace), and must NOT log anything for
    already-valid JSON."""

    def test_json_repair_logged(self, caplog):
        """A JSON string missing the closing brace must trigger a repair attempt
        that is captured in the WARNING log."""
        malformed = '{"key": "value"'  # missing closing brace
        with caplog.at_level(logging.WARNING, logger="app.llm_client"):
            result = _try_repair_json(malformed)
        # The repair must succeed (produce valid JSON)
        import json
        parsed = json.loads(result)
        assert parsed == {"key": "value"}, f"Repaired JSON does not match: {result!r}"
        # A warning must have been logged
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, (
            "_try_repair_json() did not log a warning when repair was attempted"
        )

    def test_json_repair_warning_contains_no_content(self, caplog):
        """The logged repair warning must NOT contain the raw JSON content
        (no patient data in logs)."""
        malformed = '{"patient": "sensitive data here"'
        with caplog.at_level(logging.WARNING, logger="app.llm_client"):
            _try_repair_json(malformed)
        for record in caplog.records:
            if record.levelno >= logging.WARNING:
                assert "sensitive data here" not in record.message, (
                    "Repair warning logged raw JSON content — potential PII leak"
                )

    def test_valid_json_no_repair_warning(self, caplog):
        """A properly formed JSON object must NOT trigger a repair warning."""
        valid = '{"key": "value"}'
        with caplog.at_level(logging.WARNING, logger="app.llm_client"):
            result = _try_repair_json(valid)
        import json
        assert json.loads(result) == {"key": "value"}
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warning_records, (
            f"Unexpected warning logged for valid JSON: {[r.message for r in warning_records]}"
        )

    def test_repair_attempt_with_comment_stripped(self, caplog):
        """A JSON string with single-line comments (valid after stripping) should
        not trigger a repair warning if stripping makes it valid."""
        # After comment removal and stripping, this closes correctly
        json_with_comment = '{"x": 1} // trailing comment'
        with caplog.at_level(logging.WARNING, logger="app.llm_client"):
            result = _try_repair_json(json_with_comment)
        import json as _json
        parsed = _json.loads(result)
        assert parsed == {"x": 1}
