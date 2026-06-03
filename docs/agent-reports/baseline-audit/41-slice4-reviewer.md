# Slice 4 Reviewer Report — HL7 Input Boundary Enforcement

**Session type:** Security-reviewer — Slice 4 gate
**Reviewer mode:** Read-only
**Worker report reviewed:** `40-slice4-worker.md`
**Files inspected:** `app/hl7_parser.py`, `app/fhir_builder.py`, `app/api.py`, `tests/test_slice4_hl7_boundary.py`
**Verdict:** **MERGEABLE**

---

## Sign-off Conditions Verified

| Plan requirement | Implementation location | Verified |
|---|---|---|
| Parser rejects >500 OBX with logged warning | `hl7_parser.py:200-211` — `_MAX_OBX_COUNT = 500`, pre-loop count, `logger.warning()` + `ValueError` | PASS |
| OBX NM + non-numeric value skipped + warned | `hl7_parser.py:286-296` — `float(value_raw.strip())` guard with `logger.warning()` + `continue` | PASS |
| Missing PID raises parse error | `hl7_parser.py:111-126` — `ValueError` for missing PID segment; secondary check for empty PID-3 | PASS |
| `hl7_ts_to_iso()` rejects invalid date fields | `fhir_builder.py:26-46`, `:58-68` — month/day/hour/minute range-validated with descriptive `ValueError` | PASS |
| API rejects HL7 missing PID/OBX with 400 | `api.py:441-451` — two `HTTPException(status_code=400)` guards with descriptive `detail` | PASS |

---

## Test Quality — PASS

30 tests. Real assertions: `pytest.raises(ValueError, match="501")` + `caplog` warning content; `observations == []` + warning logged; API `status_code == 400` + `"PID"` in response body. Boundary tests: exactly 500 OBX accepted, 501 rejected; midnight `00:00` accepted, hour 24 rejected, minute 60 rejected.

---

## Scope Discipline — PASS

Only `app/hl7_parser.py`, `app/fhir_builder.py`, `app/api.py` modified. All forbidden files untouched.

---

## Implementation Variance

API check uses substring presence (`"PID|" not in text`) rather than segment tokenizing. Functionally equivalent for the threat model — `"PID|"` cannot appear inside a field value in a valid HL7 message since `|` is the field separator. Accepted.

---

## Non-Blocking Notes

1. `_parse_patient` reads PID-3 twice — consolidation possible but no security impact.
2. New `.strip()` on `patient["id"]` is an improvement; confirmed by test.

---

## Verdict

**MERGEABLE.** All five sign-off conditions satisfied. Scope clean. No blocking findings.
