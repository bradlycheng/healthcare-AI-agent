from typing import Dict, Any, Optional

# Clinical Rules Definition
# code: { limit, op, msg, level, expected_units }
# expected_units: case-insensitive list of acceptable OBX units for this rule.
# If the caller passes a non-empty unit that is NOT in this set, the alert is
# suppressed (returns None). An empty/missing unit preserves legacy behavior
# (alert fires) so existing callers without unit data are unaffected.
CLINICAL_RULES = {
    # Troponin I (Cardiac)
    # Conservative set: ng/dL is NOT a standard Troponin unit and is excluded.
    '49563-0': {
        'limit': 0.04,
        'op': '>',
        'msg': 'CRITICAL: Elevated Troponin - Possible Myocardial Infarction',
        'level': 'CRITICAL',
        'expected_units': ['ng/mL', 'ng/L', 'ug/L', 'pg/mL'],
    },
    # Glucose (Metabolic)
    '2345-7': {
        'limit': 140,
        'op': '>',
        'msg': 'High Glucose - Hyperglycemia',
        'level': 'WARNING',
        'expected_units': ['mg/dL', 'mmol/L'],
    },
    '2339-0': {  # Alternative Glucose Code
        'limit': 140,
        'op': '>',
        'msg': 'High Glucose - Hyperglycemia',
        'level': 'WARNING',
        'expected_units': ['mg/dL', 'mmol/L'],
    },
    # Potassium (Electrolytes)
    '6298-4': {
        'limit': 5.5,
        'op': '>',
        'msg': 'High Potassium - Hyperkalemia Risk',
        'level': 'CRITICAL',
        'expected_units': ['mEq/L', 'mmol/L'],
    },
}


def check_alert(code: str, value: Any, unit: str = "") -> Optional[Dict[str, str]]:
    """
    Evaluate a lab result against clinical rules.
    Returns a dict with alert details if triggered, else None.

    Parameters
    ----------
    code  : LOINC observation code
    value : Observation value; must be numeric to trigger a threshold alert
    unit  : OBX unit string (OBX-6).  When non-empty, compared case-insensitively
            against the rule's expected_units list.  If the unit is present but not
            in expected_units, the alert is suppressed and None is returned.
            When unit is empty the function preserves legacy behavior and allows
            the alert to fire -- no governance side-effect is emitted here because
            this function has no request/session context.

    This function is intentionally pure: no side effects, no logging, no imports of
    governance or audit modules.  Governance logging for unit mismatch is deferred
    to agent.py (run_oru_pipeline has request context); see worker report
    docs/agent-reports/baseline-audit/20-worker-slice2-alert-unit-validation.md.
    """
    if code not in CLINICAL_RULES:
        return None

    rule = CLINICAL_RULES[code]
    print(f"DEBUG ALERT CHECK: Code={code}, Value={value}, Unit={unit!r}, Rule={rule}", flush=True)

    # Unit compatibility check -- only when caller provides a non-empty unit.
    # Empty unit preserves backward-compatible behavior (no governance side effect).
    normalized_unit = unit.strip().lower() if unit else ""
    if normalized_unit:
        expected = [u.strip().lower() for u in rule.get('expected_units', [])]
        if expected and normalized_unit not in expected:
            # Unit is present but incompatible: suppress alert.
            # Governance logging deferred -- no request context available here.
            return None

    try:
        # Convert to float for comparison if it's a number
        val_float = float(value)

        limit = rule['limit']
        operator = rule['op']

        triggered = False
        if operator == '>' and val_float > limit:
            triggered = True
        elif operator == '<' and val_float < limit:
            triggered = True

        if triggered:
            return {
                'message': rule['msg'],
                'level': rule['level'],
                'code': code
            }

    except (ValueError, TypeError):
        # Value wasn't a number, skip quantitative check
        pass

    return None
