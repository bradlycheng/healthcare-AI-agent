# Agent Report: narrow-worker -- Slice 1 HL7 Note Extraction Warden Boundary

## Assignment

Implement Slice 1 from `docs/agent-reports/baseline-audit/00-lead-hardening-plan.md`.

Wrap the `hl7_note_extraction()` LLM call in a Warden request scope so clinical-note
PHI (NTE-3, OBX-5) is tokenized before reaching the model. Add a
`register_identifiers()` helper that covers patients not yet persisted to the DB.

## Files Inspected

- docs/agent-reports/baseline-audit/00-lead-hardening-plan.md
- app/warden.py
- app/agent.py
- app/llm_gateway.py (read-only, not changed)
- app/hl7_parser.py (read-only, not changed)
- app/security_validation.py
- tests/test_e2e_warden.py (pattern reference)
- tests/test_hl7_guard.py (pattern reference)

## Files Changed

- app/warden.py -- added `WardenContext.register_identifiers(patient: dict)` method
- app/agent.py -- wrapped hl7_note_extraction() call in Warden request_scope; added imports
- tests/test_hl7_note_extraction_warden.py -- new test file (3 tests)

## Current Flow (after patch)

When `_needs_ai_analysis()` is True:

1. Build prompt via `_build_llm_prompt()` (unchanged)
2. Create a minimal `IntentGrant` scoped to `hl7_ingestion` (no tool access, no DB rows)
3. Enter `warden.request_scope(grant=ingestion_grant)`
4. Call `warden_ctx.register_identifiers(patient)` -- inserts full name, patient ID, and DOB
   into the token map before the DB write, so brand-new patients are covered
5. Call `warden_ctx.anonymize(prompt)` -- tokenizes all known PHI in the notes block
6. Call `hl7_note_extraction(safe_prompt)` with the tokenized prompt
7. OUT-GATE: serialize returned dict to JSON -> `warden_ctx.deanonymize()` -> parse back
   Restores any tokens in LLM output fields. Does NOT call `anonymize_json()` on output.

`run_oru_pipeline()` signature and return structure are unchanged.

## Constraints Verified

- run_oru_pipeline() signature and return dict keys unchanged
- app/llm_gateway.py not touched
- app/hl7_parser.py not touched
- anonymize_json() is NOT called on LLM output
- register_identifiers() checks get_token() before adding mapping (no duplicate remapping)
- Patient identifiers registered BEFORE anonymize(prompt) is called

## Tests Added

All 3 tests in tests/test_hl7_note_extraction_warden.py pass:

1. test_patient_name_not_in_note_extraction_prompt -- patient name in NTE-3; prompt verified not to contain first or last name
2. test_new_patient_not_in_db_still_tokenized -- WardenAnalyzer mocked to return empty token map; OBX-5 TX note containing patient name; prompt verified clean
3. test_warden_scope_not_entered_when_no_text_fields -- numeric-only OBX message; hl7_note_extraction mocked and asserted not_called()

50 pre-existing tests continue to pass -- no regressions.

## Residual Risks

- Warden scope covers hl7_note_extraction() only; the notes_block is not persisted to DB in
  tokenized form (raw text still stored via the observation notes field). This is by design
  for this slice -- DB storage is a separate concern tracked under raw HL7 encryption (deferred).
- register_identifiers() covers first+last name, patient ID, and DOB. Provider names from
  the OBR segment (ordering provider) are not registered here. If a provider name appears in
  a clinical note and is not yet in the DB visits table, it will not be tokenized.
  Tracked as follow-up item for a later hardening slice.

## Open Questions

None for this slice.

---

## Rework: C1+C3 Fixes

**Date:** 2026-06-02
**Triggered by:** Reviewer report `11-reviewer-slice1-security-pass.md` (NOT MERGEABLE)
**Items addressed:** C1 (post-deanonymize PHI validation) and C3 (missing LLM output deanonymization test)
**Items deferred:** C2 (provider name registration) -- documented below

---

### C2 Provider Names -- Deferred (Documented)

Provider names from OBR segments (ordering provider, performing provider) are not
registered by `register_identifiers()`. The current HL7 parser (`parse_oru()`) does not
extract OBR provider names into the runtime `patient` or `observation` structures.
Fixing provider tokenization cleanly would require changing the parsing layer and/or
the data shape passed to `register_identifiers()`. That is out of scope for Slice 1.

This gap is tracked as an existing residual risk in the original worker report above.
A future hardening slice should extend `hl7_parser.py` to surface OBR provider fields
and then pass them to `register_identifiers()`.

---

### Fix 1 -- Post-Anonymize Completeness Check (C1 partial / W3)

**Location:** `app/agent.py`, inside the Warden `request_scope` block, after `warden_ctx.anonymize(prompt)`.

After `safe_prompt = warden_ctx.anonymize(prompt)`, a completeness check now verifies
that none of the current patient's known raw identifiers (full name, first name, last name,
patient ID, DOB -- when non-empty) appear as literal strings in `safe_prompt`.

If any raw PHI is detected in `safe_prompt`:
- `llm_raw` is set to `{}` immediately
- A safe warning is printed to stderr: `"WARDEN: PHI detected in prompt after anonymize -- skipping LLM call"`
- The PHI value itself is never included in the warning message
- No exception is raised; the pipeline continues without LLM enrichment

If the check passes, the normal LLM call proceeds.

---

### Fix 2 -- Post-Deanonymize PHI Validation on LLM Output (C1)

**Location:** `app/agent.py`, inside the Warden `request_scope` block, after `_json.loads(warden_ctx.deanonymize(llm_raw_str))`.

After deanonymizing the LLM output and parsing it back to a dict, the result is
serialized to a JSON string and checked for the same set of raw patient identifiers.

If any raw PHI is detected in the deanonymized LLM output:
- `llm_raw` is set to `{}` immediately
- A safe warning is printed to stderr: `"WARDEN: PHI detected in LLM output after deanonymize -- discarding"`
- The PHI value itself is never included in the warning message
- No exception is raised; the pipeline continues without LLM enrichment

Both completeness checks use the same identifier list: full name, first name, last name,
patient ID, and DOB. Each is only checked when non-empty to avoid false positives on
empty-string matches.

---

### Fix 3 -- New Tests Added (C3)

Two new test classes added to `tests/test_hl7_note_extraction_warden.py`:

**`TestLlmOutputTokensDeanonymized.test_llm_output_tokens_deanonymized`**
- Creates a real PHI token using the `<<PHI_PAT_...>>` format
- Mocks `hl7_note_extraction()` to return a dict containing that token in a `new_observations` value field
- Patches `WardenAnalyzer.build_token_map` to return a pre-seeded `PHITokenMap` that maps the token to the real patient name
- Verifies that the raw token does NOT appear as-is in the `ai_analysis` output
- Acceptable outcomes: token restored to real name, or redacted to `TOKEN_REDACTION`

**`TestRawPhiInLlmOutputDiscarded.test_raw_phi_in_llm_output_discarded`**
- Mocks `hl7_note_extraction()` to return a dict containing the patient's real first name as a string value (simulating LLM echoing raw PHI instead of a token)
- Verifies that `ai_analysis` is `{}` or empty (discarded)
- Verifies that no `AI_EXTRACTED` observation in `structured_observations` contains the patient's first name

---

### Test Results After Rework

```
tests/test_hl7_note_extraction_warden.py  5/5 passed (3 original + 2 new)
tests/test_e2e_warden.py                 30/30 passed
tests/test_hl7_guard.py                  10/10 passed
tests/test_token_guard.py                10/10 passed
Total: 55/55 passed, 0 regressions
```

---

### Constraints Verified

- `run_oru_pipeline()` signature unchanged
- `run_oru_pipeline()` return dict keys unchanged
- No exception raised from PHI checks -- pipeline always continues
- Warning messages do not include PHI values
- `app/warden.py` not touched
- Three original Slice 1 tests pass unchanged
