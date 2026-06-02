# Agent Report: security-reviewer -- Slice 1 Rework (Second Pass)

## Assignment

Second-pass security review of Slice 1 rework. First pass blocked merge
(see 11-reviewer-slice1-security-pass.md). This pass verifies C1 and C3 fixes only.

## Files Inspected

- app/agent.py
- tests/test_hl7_note_extraction_warden.py
- app/llm_client.py (contract reference)
- docs/agent-reports/baseline-audit/10-worker-slice1-hl7-warden-boundary.md (rework section)

## Files Changed

None (read-only review)

---

## C1 -- Post-Deanonymize PHI Validation: FIXED

Implementation at app/agent.py (post-anonymize check and post-deanonymize check):
- Check is in the correct location (after deanonymize, before merge)
- Warning message does not include PHI value
- Sets llm_raw = {} and continues without raising
- Identifier list built correctly (full name, first, last, id, dob -- non-empty only)
- Output re-serialized to JSON string before check to catch nested PHI
- No bypass paths identified

False positive risk: minimal. Exact string match on specific patient identifiers.
Common clinical terms do not match. If a patient name appears naturally in LLM output
(e.g., "St. Johns Hospital"), discarding the result is correct defense-in-depth.

## C3 -- LLM Output Deanonymization Tests: FIXED

test_llm_output_tokens_deanonymized:
- Creates real PHI token, seeds PHITokenMap, mocks LLM to return token in observations
- Asserts raw token does NOT appear in ai_analysis output
- Asserts token is either restored to real name or redacted (TOKEN_REDACTION)
- Mocks set up correctly; test would catch regression

test_raw_phi_in_llm_output_discarded:
- Mocks LLM to return raw patient first_name in observation value
- Asserts ai_analysis is {} (discarded)
- Asserts no AI_EXTRACTED observation contains the raw name
- Mocks correct; test would catch regression

## C2 -- Provider Names: DEFERRED (Documented)

Worker report rework section clearly states:
- OBR provider names not registered
- Reason: hl7_parser.py does not extract OBR provider names into runtime structures
- Future work: extend hl7_parser.py to surface OBR fields; pass to register_identifiers()
Deferral is acceptable.

## Remaining Deferred Warnings

W1 (5-min grant TTL): remains. Acceptable low-urgency deferral.
W2 (governance event logging): remains. Acceptable deferral to governance-hardening slice.

## New Issues Found

None.

## Regression Results

55/55 pass (5 Slice 1 + 30 test_e2e_warden + 10 test_hl7_guard + 10 test_token_guard).
Zero regressions.

---

## Sign-Off Condition

**MERGEABLE.**

C1 fixed correctly. C3 tests comprehensive and correctly mocked. C2 deferred with clear
documentation. No new issues introduced. All tests pass.
