"""
Slice 1 -- HL7 Note Extraction Warden Boundary Tests

Verifies that the Warden IN-GATE correctly tokenizes patient PHI before
any string is passed to hl7_note_extraction(), including for patients
who are not yet persisted to the database.

Tests:
    1. test_patient_name_not_in_note_extraction_prompt
    2. test_new_patient_not_in_db_still_tokenized
    3. test_warden_scope_not_entered_when_no_text_fields

Usage:
    python -m pytest tests/test_hl7_note_extraction_warden.py -v
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Shared HL7 fixtures
# ---------------------------------------------------------------------------

def _make_hl7_with_nte(first: str, last: str, patient_id: str = "P-TEST-001") -> str:
    """HL7 ORU with patient name in PID and also embedded in an NTE-3 note."""
    return "\r".join([
        "MSH|^~\\&|LAB|HOSP|APP|FAC|20260101120000||ORU^R01|MSG001|P|2.5.1",
        f"PID|1||{patient_id}||{last}^{first}||19800601|F",
        "OBR|1||ORD001|CBC^Complete Blood Count",
        "OBX|1|NM|718-7^Hemoglobin||12.5|g/dL|12-16|N|||F",
        f"NTE|1|L|Patient {first} {last} reports mild fatigue. Follow up in 2 weeks.",
    ]) + "\r"


def _make_hl7_obx_text(first: str, last: str, patient_id: str = "P-TEST-002") -> str:
    """HL7 ORU with patient name embedded in an OBX-5 text field (TX type)."""
    return "\r".join([
        "MSH|^~\\&|LAB|HOSP|APP|FAC|20260101120000||ORU^R01|MSG002|P|2.5.1",
        f"PID|1||{patient_id}||{last}^{first}||19850315|M",
        "OBR|1||ORD002|NOTE^Clinical Note",
        f"OBX|1|TX|NOTE^Clinical note||{first} {last} presented with chest tightness. BP elevated.||||||F",
    ]) + "\r"


def _make_hl7_numeric_only(patient_id: str = "P-TEST-003") -> str:
    """HL7 ORU with only numeric OBX fields -- no TX/FT/ST/ED types, no NTE notes."""
    return "\r".join([
        "MSH|^~\\&|LAB|HOSP|APP|FAC|20260101120000||ORU^R01|MSG003|P|2.5.1",
        "PID|1||P-TEST-003||Smith^John||19750720|M",
        "OBR|1||ORD003|CBC^Complete Blood Count",
        "OBX|1|NM|718-7^Hemoglobin||14.2|g/dL|13.5-17.5|N|||F",
        "OBX|2|NM|6690-2^WBC||7.5|10^3/uL|4.5-11.0|N|||F",
        "OBX|3|NM|789-8^RBC||4.8|10^6/uL|4.5-5.5|N|||F",
    ]) + "\r"


# ---------------------------------------------------------------------------
# Test 1: Patient name in NTE-3 must be absent from the hl7_note_extraction prompt
# ---------------------------------------------------------------------------

class TestPatientNameNotInNoteExtractionPrompt:
    """PHI in NTE-3 clinical notes must be tokenized before the LLM sees them."""

    def test_patient_name_not_in_note_extraction_prompt(self):
        """Patient first/last name injected in NTE-3 must NOT appear in the
        string passed to hl7_note_extraction()."""
        first = "Eleanor"
        last = "Whitmore"
        hl7_text = _make_hl7_with_nte(first, last)

        captured_prompt = {}

        def fake_hl7_note_extraction(prompt: str):
            captured_prompt["value"] = prompt
            return {"thought_process": "test", "new_observations": []}

        with patch(
            "app.agent.hl7_note_extraction",
            side_effect=fake_hl7_note_extraction,
        ):
            from app.agent import run_oru_pipeline
            run_oru_pipeline(hl7_text, use_llm=True, persist=False)

        assert "value" in captured_prompt, (
            "hl7_note_extraction() was never called — check _needs_ai_analysis()"
        )

        prompt_text = captured_prompt["value"]
        assert first not in prompt_text, (
            f"Patient first name '{first}' leaked into hl7_note_extraction prompt"
        )
        assert last not in prompt_text, (
            f"Patient last name '{last}' leaked into hl7_note_extraction prompt"
        )
        full_name = f"{first} {last}"
        assert full_name not in prompt_text, (
            f"Full patient name '{full_name}' leaked into hl7_note_extraction prompt"
        )


# ---------------------------------------------------------------------------
# Test 2: New patient (not in DB) must still have their name tokenized
# ---------------------------------------------------------------------------

class TestNewPatientNotInDbStillTokenized:
    """register_identifiers() must cover patients not yet in the DB."""

    def test_new_patient_not_in_db_still_tokenized(self):
        """Patient whose name appears in an OBX-5 TX field but is NOT yet
        persisted to the DB must still have their name absent from the prompt
        passed to hl7_note_extraction()."""
        first = "Percival"
        last = "Drummond"
        hl7_text = _make_hl7_obx_text(first, last)

        captured_prompt = {}

        def fake_hl7_note_extraction(prompt: str):
            captured_prompt["value"] = prompt
            return {"thought_process": "test", "new_observations": []}

        # Use a non-existent DB so the patient is guaranteed not to be in it.
        # This exercises the register_identifiers() path that handles new patients.
        with patch(
            "app.agent.hl7_note_extraction",
            side_effect=fake_hl7_note_extraction,
        ):
            with patch("app.warden.WardenAnalyzer") as MockAnalyzer:
                # Make the analyzer return an empty token map (simulates no DB records)
                from app.warden import PHITokenMap
                mock_analyzer_instance = MagicMock()
                mock_analyzer_instance.build_token_map.return_value = PHITokenMap(
                    request_id="req_test_new_patient"
                )
                MockAnalyzer.return_value = mock_analyzer_instance

                from app.agent import run_oru_pipeline
                run_oru_pipeline(hl7_text, use_llm=True, persist=False)

        assert "value" in captured_prompt, (
            "hl7_note_extraction() was never called — check _needs_ai_analysis()"
        )

        prompt_text = captured_prompt["value"]
        assert first not in prompt_text, (
            f"New patient first name '{first}' leaked into prompt despite register_identifiers()"
        )
        assert last not in prompt_text, (
            f"New patient last name '{last}' leaked into prompt despite register_identifiers()"
        )
        full_name = f"{first} {last}"
        assert full_name not in prompt_text, (
            f"New patient full name '{full_name}' leaked into prompt despite register_identifiers()"
        )


# ---------------------------------------------------------------------------
# Test 3: Warden scope not entered when no text fields
# ---------------------------------------------------------------------------

class TestWardenScopeNotEnteredWhenNoTextFields:
    """When _needs_ai_analysis() is False, hl7_note_extraction must never be called."""

    def test_warden_scope_not_entered_when_no_text_fields(self):
        """HL7 message with only numeric OBX fields and no NTE notes must not
        trigger a call to hl7_note_extraction() at all."""
        hl7_text = _make_hl7_numeric_only()

        mock_extractor = MagicMock(return_value={"thought_process": "test", "new_observations": []})

        with patch("app.agent.hl7_note_extraction", mock_extractor):
            from app.agent import run_oru_pipeline
            run_oru_pipeline(hl7_text, use_llm=True, persist=False)

        mock_extractor.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4 (C3): LLM output tokens are deanonymized before reaching caller
# ---------------------------------------------------------------------------

class TestLlmOutputTokensDeanonymized:
    """Tokens in LLM output must be restored (or redacted) -- never passed through raw."""

    def test_llm_output_tokens_deanonymized(self):
        """Mock hl7_note_extraction() to return a response whose new_observations
        value field contains a PHI token. Verify that the token is restored to
        the real patient name in the returned ai_analysis dict (not passed through
        as the raw token string)."""
        first = "Nathaniel"
        last = "Pemberton"
        hl7_text = _make_hl7_with_nte(first, last)

        # Create a real PHI token using the same format as _new_phi_token()
        import secrets as _secrets
        phi_token = f"<<PHI_PAT_{_secrets.token_hex(10).upper()}>>"

        def fake_hl7_note_extraction(prompt: str):
            # Return a response that contains the PHI token in a value field
            return {
                "thought_process": "test deanonymization",
                "new_observations": [
                    {"code": "SYMPTOM", "display": "Patient Name Ref", "value": phi_token, "unit": ""},
                ]
            }

        with patch("app.agent.hl7_note_extraction", side_effect=fake_hl7_note_extraction):
            # Patch the Warden's anonymizer.deanonymize so we can inject a known
            # token -> real_value mapping.
            from app.warden import PHITokenMap, WardenAnonymizer, WardenAnalyzer

            real_token_map = PHITokenMap(request_id="req_test_deanon")
            # Register the fake token as mapping back to the real patient name
            real_token_map.add_mapping(
                f"{first} {last}",
                phi_token,
                field_type="patient_name",
                output_authorized=True,
            )

            original_build = WardenAnalyzer.build_token_map

            def fake_build_token_map(self_inner, grant=None):
                # Return our pre-seeded token map so deanonymize() knows the mapping
                real_token_map._request_id = grant.request_id if grant else ""
                # Fix the request_id in the token record too
                for token, record in real_token_map._token_records.items():
                    from app.security_validation import TokenRecord
                    real_token_map._token_records[token] = TokenRecord(
                        request_id=real_token_map._request_id,
                        token=record.token,
                        field_type=record.field_type,
                        source=record.source,
                        output_authorized=record.output_authorized,
                    )
                return real_token_map

            with patch.object(WardenAnalyzer, "build_token_map", fake_build_token_map):
                from app.agent import run_oru_pipeline
                result = run_oru_pipeline(hl7_text, use_llm=True, persist=False)

        ai_analysis = result.get("ai_analysis", {})
        new_obs = ai_analysis.get("new_observations", [])

        # The raw PHI token must NOT appear as-is in any value field of the output.
        # It must be either restored to the real name or redacted to TOKEN_REDACTION.
        from app.token_guard import TOKEN_REDACTION
        for ob in new_obs:
            val = ob.get("value", "")
            assert val != phi_token, (
                f"Raw PHI token '{phi_token}' was passed through to ai_analysis output "
                f"without deanonymization"
            )
            # Acceptable outcomes: real name restored, or redacted to TOKEN_REDACTION
            assert val in (f"{first} {last}", TOKEN_REDACTION) or "<<PHI_" not in val, (
                f"Token in output was neither restored nor properly redacted: {val!r}"
            )


# ---------------------------------------------------------------------------
# Test 5 (C1): Raw PHI in LLM output causes llm_raw to be discarded
# ---------------------------------------------------------------------------

class TestRawPhiInLlmOutputDiscarded:
    """If the LLM returns raw patient PHI (not a token) in output, llm_raw must be discarded."""

    def test_raw_phi_in_llm_output_discarded(self):
        """Mock hl7_note_extraction() to return a dict whose new_observations
        contains the patient's real first name as a string value. Verify that
        llm_raw is discarded (set to {} or equivalent) and is NOT merged into
        structured_observations."""
        first = "Josephine"
        last = "Wentworth"
        hl7_text = _make_hl7_with_nte(first, last)

        def fake_hl7_note_extraction_phi_leak(prompt: str):
            # Simulate the LLM echoing back the patient's real first name
            # (i.e., the token was not used -- raw PHI leaked into output)
            return {
                "thought_process": "test phi in output",
                "new_observations": [
                    {"code": "SYMPTOM", "display": "Patient Report", "value": first, "unit": ""},
                ]
            }

        with patch("app.agent.hl7_note_extraction", side_effect=fake_hl7_note_extraction_phi_leak):
            from app.agent import run_oru_pipeline
            result = run_oru_pipeline(hl7_text, use_llm=True, persist=False)

        # llm_raw should have been discarded -- ai_analysis must be {} or empty
        ai_analysis = result.get("ai_analysis", {})
        assert ai_analysis == {} or not ai_analysis.get("new_observations"), (
            f"Expected llm_raw to be discarded when PHI detected in output, "
            f"but ai_analysis was: {ai_analysis!r}"
        )

        # The raw PHI first name must not appear as a value in structured_observations
        # from an AI-extracted source (it may appear from HL7 parsing, which is expected)
        ai_obs = [
            ob for ob in result.get("structured_observations", [])
            if ob.get("source") == "AI_EXTRACTED"
        ]
        for ob in ai_obs:
            val = str(ob.get("value", ""))
            assert first not in val, (
                f"Patient first name '{first}' appeared in AI_EXTRACTED observation "
                f"value after PHI-in-output discard: {ob!r}"
            )


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    test_classes = [
        ("Test 1: Name not in prompt (NTE-3)", TestPatientNameNotInNoteExtractionPrompt),
        ("Test 2: New patient not in DB tokenized", TestNewPatientNotInDbStillTokenized),
        ("Test 3: No text fields -- extractor skipped", TestWardenScopeNotEnteredWhenNoTextFields),
        ("Test 4 (C3): LLM output tokens deanonymized", TestLlmOutputTokensDeanonymized),
        ("Test 5 (C1): Raw PHI in LLM output discarded", TestRawPhiInLlmOutputDiscarded),
    ]

    total = 0
    passed = 0
    failed = 0

    print("=" * 70)
    print("  Slice 1 -- HL7 Note Extraction Warden Boundary Tests")
    print("=" * 70)
    print()

    for section_name, cls in test_classes:
        print(f"--- {section_name} ---")
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for method_name in sorted(methods):
            total += 1
            test_fn = getattr(instance, method_name)
            try:
                test_fn()
                passed += 1
                print(f"  [PASS] {method_name}")
            except AssertionError as e:
                failed += 1
                print(f"  [FAIL] {method_name}: {e}")
            except Exception as e:
                failed += 1
                print(f"  [ERROR] {method_name}: {traceback.format_exc()}")
        print()

    print("=" * 70)
    print(f"  Results: {passed}/{total} passed, {failed} failed")
    print("=" * 70)
