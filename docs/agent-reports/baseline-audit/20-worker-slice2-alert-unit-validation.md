# Worker Report: Slice 2 -- Alert Unit Compatibility Validation

Date: 2026-06-02
Agent: narrow-worker (Slice 2)
Model: sonnet
Assignment: Implement unit compatibility validation in check_alert() per 00-lead-hardening-plan.md Slice 2

---

## Files Changed

| File | Change |
| :--- | :--- |
| `app/alerts.py` | Added `expected_units` to all four CLINICAL_RULES entries; updated `check_alert()` signature to accept `unit=""` parameter; added case-insensitive, whitespace-stripped unit check |
| `app/agent.py` | Updated single check_alert() call site (line 350) to pass `ob.get("unit", "")` as third argument |
| `tests/test_alert_unit_validation.py` | New file -- 22 tests covering all required cases and edge cases |

## Files NOT Changed

app/hl7_parser.py, app/db.py, app/warden.py, app/llm_gateway.py -- as required by scope.

---

## Implementation Summary

### app/alerts.py

`expected_units` added to all four rule entries with conservative, clinically accurate values:

- **49563-0 (Troponin I):** `['ng/mL', 'ng/L', 'ug/L', 'pg/mL']`
  `ng/dL` is explicitly excluded -- it is not a standard Troponin reporting unit and was called out as a known exclusion in the plan.
- **2345-7 (Glucose):** `['mg/dL', 'mmol/L']`
- **2339-0 (Glucose alt code):** `['mg/dL', 'mmol/L']`
- **6298-4 (Potassium):** `['mEq/L', 'mmol/L']`

`check_alert()` signature changed backward-compatibly to `check_alert(code, value, unit="")`.

Unit check logic:
1. Strip and lower-case the incoming unit string.
2. If the normalized unit is empty (caller passed `""`, `" "`, or nothing at all), skip the unit check entirely -- alert fires on value alone. This is the backward-compatible path.
3. If the normalized unit is non-empty, compare it case-insensitively against the rule's `expected_units` list (also normalized).
4. If the unit is not in `expected_units`, return `None` (alert suppressed). Observation is still stored -- only alert triggering is gated.

The function remains **pure**: no side effects, no logging, no imports of governance or audit modules.

### app/agent.py

One line changed (line 350):
```
# before
alert = check_alert(ob.get("code"), ob.get("value"))
# after
alert = check_alert(ob.get("code"), ob.get("value"), ob.get("unit", ""))
```
No other changes to agent.py.

---

## Governance Logging -- Deferred

`check_alert()` has no request or session context. Importing `emit_governance_event()` inside `alerts.py` would require fabricating a request ID or threading broad context changes through the call stack -- both out of scope for Slice 2 and contrary to the design constraint in the plan.

If governance logging for unit mismatch events is required, the correct location is `run_oru_pipeline()` in `app/agent.py`, which already holds an active Warden request scope and a real request ID. The pattern would be:

```python
alert = check_alert(ob.get("code"), ob.get("value"), ob.get("unit", ""))
if alert is None and ob.get("unit"):
    # check_alert suppressed due to unit mismatch -- log governance event here
    emit_governance_event(...)
```

This is deferred to a future governance-hardening slice. The current implementation is documented so future workers can locate the correct injection point without reopening alerts.py.

---

## Test Results

### New tests (tests/test_alert_unit_validation.py)

22 tests, 22 passed, 0 failed.

Tests cover:
- `test_alert_fires_valid_code_value_unit` -- Troponin + ng/mL + above threshold fires
- `test_alert_fires_valid_unit_case_insensitive` -- NG/ML matches ng/mL
- `test_alert_fires_valid_unit_with_whitespace` -- leading/trailing whitespace stripped
- `test_alert_fires_all_valid_troponin_units` -- all four expected units fire
- `test_alert_suppressed_incompatible_unit` -- mg/dL suppresses Troponin alert
- `test_alert_suppressed_nondl_variant` -- ng/dL suppressed (excluded by design)
- `test_alert_suppressed_incompatible_unit_case_insensitive` -- MG/DL still suppresses
- `test_alert_fires_missing_unit_backward_compat_no_arg` -- no unit arg fires (legacy)
- `test_alert_fires_missing_unit_backward_compat_empty_string` -- unit="" fires (legacy)
- `test_alert_fires_missing_unit_backward_compat_whitespace_only` -- whitespace-only fires (legacy)
- `test_alert_not_triggered_wrong_value_type` -- "POSITIVE" returns None (regression)
- `test_alert_not_triggered_none_value` -- None value returns None
- `test_alert_not_triggered_empty_value` -- "" value returns None
- `test_existing_rules_unaffected_glucose_mg_dl` -- Glucose/mg/dL fires
- `test_existing_rules_unaffected_glucose_mmol_l` -- Glucose/mmol/L fires
- `test_existing_rules_unaffected_glucose_alt_code` -- 2339-0/mg/dL fires
- `test_existing_rules_unaffected_glucose_incompatible_unit` -- Glucose/ng/mL suppressed
- `test_existing_rules_unaffected_potassium_meq_l` -- Potassium/mEq/L fires
- `test_existing_rules_unaffected_potassium_mmol_l` -- Potassium/mmol/L fires
- `test_existing_rules_unaffected_potassium_incompatible_unit` -- Potassium/ng/mL suppressed
- `test_existing_rules_unaffected_below_threshold_no_alert` -- sub-threshold never fires
- `test_unknown_code_returns_none` -- unknown LOINC returns None

### Regression suite

163 tests total, 163 passed, 0 failed.
Existing suites unaffected: test_e2e_warden (30), test_hl7_guard (10), test_token_guard (10),
test_hl7_note_extraction_warden (5), test_sql_guard (20), test_endpoint_governance (16),
test_security_kernel_phase1 (10), test_grant_builder (5), test_intent_classifier (5),
test_rag_calculator_guards (8), test_static_compile_imports (3), test_reference_resolver (6),
test_safe_memory (4), test_context_builder (3), test_context_memory (2), test_coverage_closure (5).

---

## Residual Risks

| ID | Severity | Description |
| :--- | :--- | :--- |
| R1 | WARNING | Governance logging for unit mismatch suppression deferred (see above). No audit trail for mismatched-unit observations in the current build. |
| R2 | WARNING | Backward-compatible path (empty unit) allows alert to fire for any numeric value above threshold regardless of unit. Existing callers that do not supply a unit receive full alert coverage -- this is intentional but means the unit gate is only active when the HL7 parser extracts OBX-6. Confirm OBX-6 is reliably surfaced by hl7_parser for all inbound messages. |
| R3 | INFORMATIONAL | A sophisticated attacker who knows the expected units can still fake a matching unit. Full defense requires LOINC registry cross-validation (out of scope). |

---

## Sign-Off Conditions Met

- Troponin LOINC code with value above threshold and incompatible unit returns None. (Verified by test_alert_suppressed_incompatible_unit and test_alert_suppressed_nondl_variant.)
- ng/dL excluded from Troponin expected_units. (Verified by test_alert_suppressed_nondl_variant.)
- All existing alert behavior on valid code/value/unit combinations unchanged. (163 regression tests pass.)
- check_alert() return structure unchanged ({message, level, code} or None).
- Observations with mismatched units still stored; only alert triggering is gated.
- check_alert() remains pure -- no side effects, no governance imports.
