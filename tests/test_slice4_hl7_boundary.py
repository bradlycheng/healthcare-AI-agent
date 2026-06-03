# tests/test_slice4_hl7_boundary.py
"""
Slice 4 — HL7 boundary / structural validation tests.

Covers:
  - OBX segment count limit (>500 rejected with logged warning)
  - OBX NM type mismatch: non-numeric value skipped with logged warning
  - Missing/empty PID causes parse failure (ValueError)
  - hl7_ts_to_iso() rejects invalid calendar components
  - API /oru/parse rejects HL7 missing PID or OBX segments with HTTP 400
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.fhir_builder import hl7_ts_to_iso


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_hl7(
    obx_count: int = 1,
    include_pid: bool = True,
    patient_id: str = "P001",
    obx_value_type: str = "NM",
    obx_value: str = "7.2",
) -> str:
    """Build a minimal valid ORU^R01 HL7 v2.5.1 message."""
    lines = [
        r"MSH|^~\&|SENDER|FAC|RCV|FAC2|20240101120000||ORU^R01|MSG001|P|2.5.1",
    ]
    if include_pid:
        lines.append(
            f"PID|1||{patient_id}^^^FAC^MR||DOE^JANE||19800101|F"
        )
    lines.append("OBR|1|||PANEL")
    for i in range(1, obx_count + 1):
        lines.append(
            f"OBX|{i}|{obx_value_type}|8867-4^Heart Rate^LN||{obx_value}|bpm|60-100|N|||F"
        )
    return "\r".join(lines) + "\r"


# ---------------------------------------------------------------------------
# Test 1 — OBX count limit
# ---------------------------------------------------------------------------

class TestHL7OversizedOBXCountRejected:
    """parse_oru() must reject messages with >500 OBX segments with a ValueError
    and log a warning."""

    def test_hl7_oversized_obx_count_rejected(self, caplog):
        """501 OBX segments must be rejected with a ValueError and a logged warning."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_count=501)
        with caplog.at_level(logging.WARNING, logger="app.hl7_parser"):
            with pytest.raises(ValueError, match="501"):
                parse_oru(hl7)

        # A warning must have been logged
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "No warning was logged for oversized OBX count"

    def test_exactly_500_obx_segments_accepted(self):
        """Exactly 500 OBX segments must be accepted (boundary condition)."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_count=500)
        patient, observations = parse_oru(hl7)
        assert len(observations) == 500

    def test_501_obx_warning_contains_count(self, caplog):
        """The logged warning must mention the count (501)."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_count=501)
        with caplog.at_level(logging.WARNING, logger="app.hl7_parser"):
            with pytest.raises(ValueError):
                parse_oru(hl7)

        combined = " ".join(r.message for r in caplog.records if r.levelno >= logging.WARNING)
        assert "501" in combined, f"Warning did not mention count 501: {combined!r}"

    def test_1_obx_segment_accepted(self):
        """A single OBX segment must be accepted normally."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_count=1)
        patient, observations = parse_oru(hl7)
        assert len(observations) == 1


# ---------------------------------------------------------------------------
# Test 2 — OBX NM type mismatch
# ---------------------------------------------------------------------------

class TestOBXValueTypeMismatchSkippedAndLogged:
    """When OBX-2 is NM but the value cannot be cast to float, the observation
    must be skipped and a WARNING must be logged."""

    def test_obx_value_type_mismatch_skipped_and_logged(self, caplog):
        """OBX-2=NM with value='abc' must be skipped with a logged warning."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_value_type="NM", obx_value="abc")
        with caplog.at_level(logging.WARNING, logger="app.hl7_parser"):
            patient, observations = parse_oru(hl7)

        assert observations == [], (
            f"Expected no observations when NM value is non-numeric, got: {observations}"
        )
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warning_records, "No warning was logged for NM type mismatch"

    def test_obx_nm_non_numeric_warning_contains_value(self, caplog):
        """The mismatch warning must reference the bad value."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_value_type="NM", obx_value="notanumber")
        with caplog.at_level(logging.WARNING, logger="app.hl7_parser"):
            parse_oru(hl7)

        combined = " ".join(r.message for r in caplog.records if r.levelno >= logging.WARNING)
        assert "notanumber" in combined or "mismatch" in combined.lower(), (
            f"Warning did not mention the bad value: {combined!r}"
        )

    def test_obx_nm_valid_numeric_accepted(self):
        """OBX-2=NM with a valid numeric value must be accepted normally."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_value_type="NM", obx_value="72.5")
        _, observations = parse_oru(hl7)
        assert len(observations) == 1
        assert observations[0]["value"] == pytest.approx(72.5)

    def test_obx_tx_non_numeric_accepted(self):
        """OBX-2=TX with a text value must be accepted (no type constraint)."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_value_type="TX", obx_value="normaltext")
        _, observations = parse_oru(hl7)
        assert len(observations) == 1
        assert observations[0]["value"] == "normaltext"

    def test_obx_nm_integer_string_accepted(self):
        """OBX-2=NM with a whole-number string must be accepted."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(obx_value_type="NM", obx_value="100")
        _, observations = parse_oru(hl7)
        assert len(observations) == 1


# ---------------------------------------------------------------------------
# Test 3 — Missing PID segment
# ---------------------------------------------------------------------------

class TestMissingPIDSegmentFailsParse:
    """parse_oru() must raise ValueError when the PID segment is absent."""

    def test_missing_pid_segment_fails_parse(self):
        """A message without a PID segment must raise ValueError."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(include_pid=False)
        with pytest.raises(ValueError, match="[Pp][Ii][Dd]"):
            parse_oru(hl7)

    def test_missing_pid_error_message_is_descriptive(self):
        """The ValueError message must mention 'PID'."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(include_pid=False)
        with pytest.raises(ValueError) as exc_info:
            parse_oru(hl7)
        assert "PID" in str(exc_info.value).upper(), (
            f"Error message did not mention PID: {exc_info.value}"
        )

    def test_valid_pid_parses_successfully(self):
        """A message with a valid PID must parse without error and return a non-empty id."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(include_pid=True, patient_id="PAT123")
        patient, _ = parse_oru(hl7)
        # The parser returns the full CX component string; verify it is non-empty
        # and includes the patient ID portion
        assert patient["id"], "Patient id must not be empty"
        assert "PAT123" in patient["id"], (
            f"Expected PAT123 to appear in patient id, got: {patient['id']!r}"
        )

    def test_message_with_pid_returns_correct_patient_id(self):
        """Patient ID from PID-3 must be present in the parsed patient dict."""
        from app.hl7_parser import parse_oru

        hl7 = _make_minimal_hl7(patient_id="XYZ999")
        patient, _ = parse_oru(hl7)
        assert patient["id"], "Patient id must not be empty"
        assert "XYZ999" in patient["id"], (
            f"Expected XYZ999 to appear in patient id, got: {patient['id']!r}"
        )


# ---------------------------------------------------------------------------
# Test 4 — Invalid HL7 timestamps
# ---------------------------------------------------------------------------

class TestInvalidHL7TimestampRejected:
    """hl7_ts_to_iso() must raise ValueError for out-of-range calendar components."""

    def test_invalid_hl7_timestamp_rejected_month_99(self):
        """Month 99 must raise ValueError."""
        with pytest.raises(ValueError, match="month"):
            hl7_ts_to_iso("20259922000000")

    def test_invalid_hl7_timestamp_rejected_month_00(self):
        """Month 00 must raise ValueError."""
        with pytest.raises(ValueError, match="month"):
            hl7_ts_to_iso("20250022000000")

    def test_invalid_hl7_timestamp_rejected_month_13(self):
        """Month 13 must raise ValueError."""
        with pytest.raises(ValueError, match="month"):
            hl7_ts_to_iso("20251322000000")

    def test_invalid_hl7_timestamp_rejected_day_99(self):
        """Day 99 must raise ValueError."""
        with pytest.raises(ValueError, match="day"):
            hl7_ts_to_iso("20250199000000")

    def test_invalid_hl7_timestamp_rejected_day_00(self):
        """Day 00 must raise ValueError."""
        with pytest.raises(ValueError, match="day"):
            hl7_ts_to_iso("20250100000000")

    def test_invalid_hl7_timestamp_rejected_hour_24(self):
        """Hour 24 must raise ValueError."""
        with pytest.raises(ValueError, match="hour"):
            hl7_ts_to_iso("20250122240000")

    def test_invalid_hl7_timestamp_rejected_minute_60(self):
        """Minute 60 must raise ValueError."""
        with pytest.raises(ValueError, match="minute"):
            hl7_ts_to_iso("20250122096000")

    def test_valid_timestamp_accepted(self):
        """A fully valid timestamp must be converted correctly."""
        result = hl7_ts_to_iso("20250122090000")
        assert result == "2025-01-22T09:00:00"

    def test_valid_date_only_accepted(self):
        """An 8-digit date string must be accepted and converted."""
        result = hl7_ts_to_iso("20250122")
        assert result == "2025-01-22"

    def test_invalid_date_only_month_99(self):
        """An 8-digit string with month 99 must raise ValueError."""
        with pytest.raises(ValueError, match="month"):
            hl7_ts_to_iso("20259922")

    def test_empty_timestamp_returns_empty(self):
        """An empty string must return empty string (not raise)."""
        assert hl7_ts_to_iso("") == ""

    def test_midnight_hour_00_accepted(self):
        """Hour 00 (midnight) is valid and must not raise."""
        result = hl7_ts_to_iso("20250101000000")
        assert result == "2025-01-01T00:00:00"

    def test_hour_23_minute_59_accepted(self):
        """Hour 23 and minute 59 are at the boundary and must be accepted."""
        result = hl7_ts_to_iso("20250101235900")
        assert result == "2025-01-01T23:59:00"


# ---------------------------------------------------------------------------
# Test 5 — API structural segment validation
# ---------------------------------------------------------------------------

class TestAPIRejectsHL7MissingRequiredSegments:
    """POST /oru/parse must return HTTP 400 when PID or OBX segments are absent."""

    def _get_test_client(self):
        from fastapi.testclient import TestClient
        from app.api import app
        return TestClient(app)

    def _make_hl7_no_pid(self) -> str:
        """HL7 message with MSH + OBX but no PID."""
        return (
            r"MSH|^~\&|SENDER|FAC|RCV|FAC2|20240101120000||ORU^R01|MSG001|P|2.5.1" + "\r"
            "OBR|1|||PANEL\r"
            "OBX|1|NM|8867-4^Heart Rate^LN||72|bpm|60-100|N|||F\r"
        )

    def _make_hl7_no_obx(self) -> str:
        """HL7 message with MSH + PID but no OBX."""
        return (
            r"MSH|^~\&|SENDER|FAC|RCV|FAC2|20240101120000||ORU^R01|MSG001|P|2.5.1" + "\r"
            "PID|1||P001^^^FAC^MR||DOE^JANE||19800101|F\r"
            "OBR|1|||PANEL\r"
        )

    def _make_valid_hl7(self) -> str:
        """Minimal valid HL7 message."""
        return (
            r"MSH|^~\&|SENDER|FAC|RCV|FAC2|20240101120000||ORU^R01|MSG001|P|2.5.1" + "\r"
            "PID|1||P001^^^FAC^MR||DOE^JANE||19800101|F\r"
            "OBR|1|||PANEL\r"
            "OBX|1|NM|8867-4^Heart Rate^LN||72|bpm|60-100|N|||F\r"
        )

    def test_api_rejects_hl7_missing_required_segments_no_pid(self):
        """API must return HTTP 400 when PID segment is missing."""
        client = self._get_test_client()
        resp = client.post(
            "/oru/parse",
            json={"hl7_text": self._make_hl7_no_pid(), "use_llm": False, "persist": False},
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing PID, got {resp.status_code}: {resp.text}"
        )
        assert "PID" in resp.text or "pid" in resp.text.lower(), (
            f"Error message did not mention PID: {resp.text}"
        )

    def test_api_rejects_hl7_missing_required_segments_no_obx(self):
        """API must return HTTP 400 when OBX segment is missing."""
        client = self._get_test_client()
        resp = client.post(
            "/oru/parse",
            json={"hl7_text": self._make_hl7_no_obx(), "use_llm": False, "persist": False},
        )
        assert resp.status_code == 400, (
            f"Expected 400 for missing OBX, got {resp.status_code}: {resp.text}"
        )
        assert "OBX" in resp.text or "obx" in resp.text.lower(), (
            f"Error message did not mention OBX: {resp.text}"
        )

    def test_api_rejects_hl7_missing_msh(self):
        """API must return HTTP 400 when MSH segment is completely missing."""
        client = self._get_test_client()
        resp = client.post(
            "/oru/parse",
            json={"hl7_text": "PID|1||P001\rOBX|1|NM|CODE||5\r", "use_llm": False, "persist": False},
        )
        assert resp.status_code == 400

    def test_api_400_response_has_detail_field(self):
        """HTTP 400 responses must include a 'detail' field."""
        client = self._get_test_client()
        resp = client.post(
            "/oru/parse",
            json={"hl7_text": self._make_hl7_no_pid(), "use_llm": False, "persist": False},
        )
        assert resp.status_code == 400
        body = resp.json()
        assert "detail" in body, f"Response body missing 'detail' key: {body}"
