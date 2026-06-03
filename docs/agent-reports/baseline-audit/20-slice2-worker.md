# Slice 2 Worker Report — Prompt Injection Hardening

**Date:** 2026-06-03
**Worker:** Narrow-worker subagent (Slice 2 scope)
**Files owned:** `app/agent.py`, `app/patient_timeline.py`, `app/security.py`
**Status:** DONE — all sign-off conditions met

---

## What Was Changed

### app/security.py — expanded INJECTION_PATTERNS (lines 8–24)

Added 5 new multi-word injection patterns to `INJECTION_PATTERNS`. Also updated the
`System:` and `Human:` patterns to use `\s*:` (matching "SYSTEM :" with a space before
the colon) instead of the bare `:` literal:

| New pattern | Regex added |
|---|---|
| `you've become` | `r"(?i)you've\s+become"` |
| `you have become` | `r"(?i)you have become"` |
| `act as if` | `r"(?i)act as if"` |
| `pretend you are` | `r"(?i)pretend you are"` |
| `pretend to be` | `r"(?i)pretend to be"` |
| `SYSTEM :` (space before colon) | Updated `r"(?i)System\s*:"` |
| `HUMAN :` (space before colon) | Updated `r"(?i)Human\s*:"` |

All patterns already use the `(?i)` inline flag, so they are case-insensitive by
construction. No changes to the `sanitize_text()` function body were needed.

Relevant diff: `app/security.py` lines 9–24 (INJECTION_PATTERNS list).

---

### app/agent.py — re-sanitize NTE-3 notes + delimiter tags (lines 121–130)

In `_build_llm_prompt()`, the inner loop that assembles the note block previously
embedded raw note strings directly into the prompt string. Changed to:

1. **Re-sanitize each note individually** via `sanitize_text(str(n))` immediately after
   extraction, before appending to the prompt. This covers the gap where NTE-3 notes
   are extracted from the already-sanitized HL7 message but the per-note sanitization
   was missing.
2. **Wrap the observation display label** used as note attribution in
   `[PATIENT_DATA]...[/PATIENT_DATA]` delimiter tags.
3. **Wrap the sanitized note text** in `[PATIENT_DATA]...[/PATIENT_DATA]` delimiter
   tags.

The one remaining `print()` in `agent.py` (line 261) outputs only an exception object
from a failed LLM call — no patient names, IDs, DOBs, or observation values — so it was
left in place as an infrastructure error log.

Relevant diff: `app/agent.py` lines 121–130 (`_build_llm_prompt()`).

---

### app/patient_timeline.py — delimiter tags + remove PII print (lines 163–196)

In `generate_journey_summary()`:

1. **Wrapped each observation display and value** in the `obs_text` f-string in
   `[PATIENT_DATA]...[/PATIENT_DATA]` tags.
2. **Wrapped the patient first+last name** in a `patient_name` variable with
   `[PATIENT_DATA]...[/PATIENT_DATA]` tags before embedding in the prompt string.
3. **Replaced the bare `print(f"Journey summary error: {e}")` call** (which could
   expose exception messages containing patient context) with a structured
   `logging.warning("Journey summary error: %s", type(e).__name__)` call that logs
   only the exception type, not its message.

Relevant diff: `app/patient_timeline.py` lines 163–196 (`generate_journey_summary()`).

---

## Test Results

**New test file:** `tests/test_slice2_prompt_injection.py`
**24 tests collected — 24 passed, 0 failed**

```
tests/test_slice2_prompt_injection.py::TestClinicalNoteInjectionBlockedBeforePrompt   3 passed
tests/test_slice2_prompt_injection.py::TestPatientNameWrappedInPrompt                 2 passed
tests/test_slice2_prompt_injection.py::TestObservationDisplayWrappedInPrompt          2 passed
tests/test_slice2_prompt_injection.py::TestMultiwordInjectionPatternsDetected        14 passed
tests/test_slice2_prompt_injection.py::TestNoPiiInDebugPrintOutput                    2 passed (+ 1 bonus)
```

**Regression run** (`python -m pytest tests/ -k "security or inject or sanitize" -v`):
24 passed, 46 deselected, 0 failures.

---

## Sign-off Checklist

| Condition | Status |
|---|---|
| NTE-3 note text re-sanitized via `sanitize_text()` immediately after extraction in `agent.py` | PASS |
| Observation display label wrapped in `[PATIENT_DATA]...[/PATIENT_DATA]` in `agent.py` | PASS |
| Note text wrapped in `[PATIENT_DATA]...[/PATIENT_DATA]` in `agent.py` | PASS |
| Patient name wrapped in `[PATIENT_DATA]...[/PATIENT_DATA]` in `patient_timeline.py` | PASS |
| Observation display + value wrapped in `[PATIENT_DATA]...[/PATIENT_DATA]` in `patient_timeline.py` | PASS |
| `you've become` pattern added | PASS |
| `you have become` pattern added | PASS |
| `act as if` pattern added | PASS |
| `pretend you are` pattern added | PASS |
| `pretend to be` pattern added | PASS |
| `SYSTEM :` (space before colon) covered | PASS |
| `HUMAN :` (space before colon) covered | PASS |
| All patterns are case-insensitive | PASS |
| No `print()` exposes patient names/IDs/DOBs/observation values in any owned file | PASS |

---

## Deferred Items

None. All sign-off conditions are met within the file ownership boundary.

Note: The `<INSTRUCTIONS>` block of the LLM prompt itself contains the word "instructions"
(as part of the static system prompt text). This is intentional static text, not patient
data, and is not subject to PII tagging.
