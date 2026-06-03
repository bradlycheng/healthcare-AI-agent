# Slice 4 Worker Report — HL7 Boundary & Structural Validation

**Session type:** Narrow-worker — Slice 4 execution
**Files modified:** `app/hl7_parser.py`, `app/fhir_builder.py`, `app/api.py`
**Artifacts written:** `tests/test_slice4_hl7_boundary.py`, `docs/agent-reports/baseline-audit/40-slice4-worker.md`

---

## Changes Made

### app/hl7_parser.py

**Lines added/changed: ~60 lines across three locations**

1. **Module-level additions (lines 1–11):** Added `import logging`, a module-level `logger = logging.getLogger(__name__)`, and a constant `_MAX_OBX_COUNT = 500`.

2. **`_parse_patient()` — PID required (lines ~111–134):** Replaced the silent `return patient` fallback when `pid is None` with `raise ValueError("HL7 message is missing required PID segment.")`. Added a secondary check immediately after: iterate `pid.pid_3`, call `_safe_value()` on the first CX component, and raise `ValueError("HL7 PID segment is missing patient ID (PID-3).")` if the result is empty. This ensures both absent PID segment and a PID segment with no patient ID are hard failures rather than silent defaults.

3. **`_parse_observations()` — OBX count limit (lines ~200–215):** Before the iteration loop, count all OBX children with `sum(1 for child in msg.children if child.name == "OBX")`. If `obx_count > 500`, call `logger.warning(...)` with the count and raise `ValueError` citing the count and the limit.

4. **`_parse_observations()` — NM value type mismatch (lines ~297–311):** After extracting `value_raw`, added a guard: if `value_type == "NM"` and `value_raw.strip()` is non-empty, attempt `float(value_raw.strip())`; on `ValueError`/`TypeError`, call `logger.warning(...)` with the bad value and the observation code, then `continue` to skip the observation entirely. A TX/FT/ED observation with non-numeric text is unaffected.

### app/fhir_builder.py

**Lines added/changed: ~35 lines inside `hl7_ts_to_iso()`**

In the 14-character datetime branch: after slicing year/month/day/hour/minute/second, convert each of month, day, hour, minute to `int` and validate:
- month: `1 <= month_i <= 12` else `ValueError`
- day: `1 <= day_i <= 31` else `ValueError`
- hour: `0 <= hour_i <= 23` else `ValueError`
- minute: `0 <= minute_i <= 59` else `ValueError`

In the 8-character date-only branch: validate month and day with the same rules.

All `ValueError` messages include the original `ts` string and the field name + range so callers and logs are unambiguous. The function no longer silently produces dates like `"2025-99-99T24:60:00"`.

### app/api.py

**Lines added/changed: ~10 lines in `/oru/parse` handler (around line 439)**

After the existing `"MSH" not in req.hl7_text` check, added two additional `HTTPException(status_code=400)` guards:
- `if "PID|" not in req.hl7_text` → `detail="Invalid HL7 message: missing required PID segment."`
- `if "OBX|" not in req.hl7_text` → `detail="Invalid HL7 message: missing required OBX segment."`

Both checks run before any parsing begins, providing a fast-path 400 for structurally incomplete messages.

---

## Test Results

### Slice 4 suite (`tests/test_slice4_hl7_boundary.py`)

```
30 passed, 0 failed
```

Test classes:
- `TestHL7OversizedOBXCountRejected` — 4 tests (501 rejected with warning + count in message, 500 accepted, 1 accepted)
- `TestOBXValueTypeMismatchSkippedAndLogged` — 5 tests (NM+abc skipped+warned, warning mentions value, NM+float accepted, TX+text accepted, NM+integer-string accepted)
- `TestMissingPIDSegmentFailsParse` — 4 tests (no PID raises, error message mentions "PID", valid PID parses, patient id contains patient ID substring)
- `TestInvalidHL7TimestampRejected` — 13 tests (month 99/00/13, day 99/00, hour 24, minute 60, valid datetime, valid date-only, bad date-only month, empty string, midnight hour-00, hour-23/minute-59)
- `TestAPIRejectsHL7MissingRequiredSegments` — 4 tests (no PID → 400, no OBX → 400, no MSH → 400, 400 body has `detail` field)

### Regression suite (`tests/ -k "hl7 or parse or fhir"`)

```
55 passed, 0 failed
```

All pre-existing tests in `test_slice1_sql_hardening.py` that matched the filter continued to pass unchanged.

---

## Sign-off Condition Checklist

| Condition | Status |
|-----------|--------|
| Parser rejects messages with >500 OBX segments (logged warning + error result) | PASS |
| OBX NM type with non-numeric value: observation skipped with logged warning | PASS |
| Missing/empty PID causes parse failure (not silent default) | PASS |
| `hl7_ts_to_iso()` rejects month > 12, day > 31, hour > 23 with ValueError | PASS |
| API rejects HL7 missing PID or OBX segments with HTTP 400 | PASS |

**Verdict: All sign-off conditions met.**
