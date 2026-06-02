# Agent Report: security-reviewer -- Slice 2 (Alert Unit Compatibility Validation)

## Assignment

Final security review of Slice 2 (alert unit compatibility validation) before merge.
Read app/alerts.py, app/agent.py (call-site region), tests/test_alert_unit_validation.py,
and the worker report. Check unit logic correctness, clinical accuracy, backward
compatibility, pure-function constraint, return structure, observation persistence,
agent.py scope, test quality, governance deferral documentation.

## Files Inspected

- app/alerts.py
- app/agent.py (lines 340-375 -- check_alert call site region)
- tests/test_alert_unit_validation.py
- docs/agent-reports/baseline-audit/20-worker-slice2-alert-unit-validation.md
- docs/agent-reports/baseline-audit/00-lead-hardening-plan.md (Slice 2 section)

## Files Changed

None (read-only review)

---

## Preliminary Note -- Worktree Artifact

The pre-Slice-2 baseline exists in a git worktree copy
(.claude/worktrees/agent-a675f2a90dba7b5f5) with the old two-argument check_alert
signature and no expected_units. This is expected and not a defect. All findings
reference production files only.

---

## Critical Findings

None. No blocking issues found.

---

## Warning Findings

**W1 -- Governance logging for unit mismatch not implemented (plan sign-off partially unmet)**

The hardening plan sign-off condition states: "Mismatch must appear in governance_events."
This condition is NOT met. check_alert() silently returns None on unit mismatch; no
emit_governance_event() call exists in the alert path or at the agent.py call site.

Deferral is acceptable because:
- Suppression behavior (return None) is correct and tested.
- check_alert() correctly has no request context -- threading one in would be out of scope.
- The correct injection point is documented in both the worker report and alerts.py docstring:
  agent.py run_oru_pipeline() after line 350, using the active Warden request scope.
- The code pattern for the future worker is provided in the worker report.
- emit_governance_event() and the governance_events table already exist in the codebase.

Acceptance condition for future governance slice: agent.py line 350 must be expanded
to call emit_governance_event() when check_alert() returns None and ob.get("unit") is
non-empty, using the active request scope already present in run_oru_pipeline().

**W2 -- DEBUG print on every alert evaluation (pre-existing)**

app/alerts.py line 70:
```
print(f"DEBUG ALERT CHECK: Code={code}, Value={value}, Unit={unit!r}, Rule={rule}", flush=True)
```
This was present before Slice 2. Not introduced by this change. Value and unit fields
are lab numerics and unit strings -- not direct PHI like patient name/ID -- but this
prints to stdout on every evaluation including tests, and could accumulate in log
aggregators. Should be replaced with structured logging at DEBUG level in a separate
cleanup slice. Not a blocker.

**W3 -- Empty-unit backward-compat path bypasses gate if OBX-6 not reliably extracted**

When OBX-6 is absent or empty in an inbound HL7 message, check_alert() fires the alert
unconditionally. The unit gate is only active when hl7_parser.py surfaces OBX-6 into
the unit field of structured_observations. This is correctly identified and deferred in
worker residual risk R2.

Acceptance condition for future audit: confirm parse_oru() reliably extracts OBX-6 and
add a test verifying unit is surfaced in structured_observations for messages with a
populated OBX-6 field.

---

## Informational Findings

**I1 -- Unit comparison logic is correct**
case-insensitive via .strip().lower() on both sides. Empty/whitespace unit normalizes
to "" (falsy), check skipped. Rule with empty expected_units list also skips check
(safe default). PASS.

**I2 -- Clinical unit accuracy**
- Troponin (49563-0): ng/mL, ng/L, ug/L, pg/mL -- correct and conservative. ng/dL
  correctly excluded (not a standard Troponin unit). PASS.
- Glucose (2345-7, 2339-0): mg/dL, mmol/L -- correct. PASS.
- Potassium (6298-4): mEq/L, mmol/L -- correct (numerically equivalent for potassium).
  PASS.

**I3 -- Return structure unchanged**
{message, level, code} or None. Identical to pre-Slice-2 structure. PASS.

**I4 -- Observation persistence unaffected**
insert_message_and_observations() at agent.py line 358 is not conditioned on alert
outcome. Observations stored regardless of check_alert() return. PASS.

**I5 -- agent.py scope correctly limited**
Only the addition of ob.get("unit", "") as third argument on line 350. No other
modifications to agent.py confirmed. PASS.

**I6 -- Test assertions are correct and meaningful**
Suppression tests use assert result is None (not just no exception). Firing tests
use assert result is not None. Incompatible units in suppression tests are genuinely
wrong for the code under test (mg/dL for Troponin, ng/mL for Potassium). Backward-
compat tests cover no-arg, empty-string, and whitespace-only variants. PASS.

**I7 -- Existing callers backward-compatible**
test_additional_systems.py calls check_alert() with two arguments. The unit="" default
preserves that behavior. No production call sites other than agent.py line 350. PASS.

**I8 -- Pure function constraint satisfied**
alerts.py imports only typing. No governance, logging, DB, or Warden imports.
No side effects beyond the pre-existing debug print (W2). PASS.

**I9 -- Governance deferral documentation sufficient**
Worker report names the injection point, provides a code pattern, and explains the
rationale. alerts.py docstring references the worker report by path. A future worker
has everything needed without reopening alerts.py internals. PASS.

---

## Summary

| ID | Severity | Finding | Disposition |
| :-- | :-- | :-- | :-- |
| W1 | WARNING | Governance logging deferred -- plan sign-off partially unmet | Acceptable -- injection point and pattern documented |
| W2 | WARNING | DEBUG print on every evaluation (pre-existing) | Pre-existing; separate cleanup item |
| W3 | WARNING | Empty-unit path bypasses gate if OBX-6 not extracted | Correctly deferred in worker report |
| I1-I9 | INFO | Unit logic, clinical accuracy, return structure, persistence, scope, tests, backward compat, pure fn, governance docs | All pass |

---

## Sign-Off Condition

**MERGEABLE.**

Core security objective achieved: Troponin observation above threshold with incompatible
unit is now suppressed. Clinical unit lists are correct and conservative. check_alert()
is pure. Return structure is unchanged. Observations are still persisted. Call-site
change in agent.py is correctly scoped to one line. Tests assert correct behavior
(suppression returns None, not just no exception). All three warnings are pre-existing
or correctly documented deferrals.

The governance logging gap (W1) is the most material deferral, but the infrastructure
to fulfill it (emit_governance_event, governance_events table, active request scope in
run_oru_pipeline) all exist and are ready for a future governance-hardening slice.
163/163 regression tests pass.
