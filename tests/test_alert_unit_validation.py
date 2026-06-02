"""
Tests for Slice 2: Alert unit compatibility validation.

Verifies that check_alert() correctly gates alerts on OBX unit compatibility
while preserving all existing behavior for callers that do not supply a unit.
"""

import pytest
from app.alerts import check_alert, CLINICAL_RULES

TROPONIN_CODE = '49563-0'
TROPONIN_THRESHOLD = CLINICAL_RULES[TROPONIN_CODE]['limit']
TROPONIN_HIGH = TROPONIN_THRESHOLD + 0.1   # 0.14 -- clearly above limit

GLUCOSE_CODE = '2345-7'
GLUCOSE_ALT_CODE = '2339-0'
GLUCOSE_THRESHOLD = CLINICAL_RULES[GLUCOSE_CODE]['limit']
GLUCOSE_HIGH = GLUCOSE_THRESHOLD + 10      # 150

POTASSIUM_CODE = '6298-4'
POTASSIUM_THRESHOLD = CLINICAL_RULES[POTASSIUM_CODE]['limit']
POTASSIUM_HIGH = POTASSIUM_THRESHOLD + 0.5  # 6.0


# ---------------------------------------------------------------------------
# test_alert_fires_valid_code_value_unit
# ---------------------------------------------------------------------------

def test_alert_fires_valid_code_value_unit():
    """Troponin above threshold with a correct unit (ng/mL) must fire an alert."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "ng/mL")
    assert result is not None, "Expected alert to fire for Troponin with ng/mL"
    assert result["level"] == "CRITICAL"
    assert result["code"] == TROPONIN_CODE
    assert "Troponin" in result["message"]


def test_alert_fires_valid_unit_case_insensitive():
    """Unit comparison must be case-insensitive (NG/ML should match ng/mL)."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "NG/ML")
    assert result is not None, "Unit match must be case-insensitive"


def test_alert_fires_valid_unit_with_whitespace():
    """Unit comparison must strip surrounding whitespace."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "  ng/mL  ")
    assert result is not None, "Unit match must strip leading/trailing whitespace"


def test_alert_fires_all_valid_troponin_units():
    """All four expected Troponin units must allow the alert to fire."""
    for unit in ['ng/mL', 'ng/L', 'ug/L', 'pg/mL']:
        result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, unit)
        assert result is not None, f"Expected alert to fire for Troponin with unit={unit!r}"


# ---------------------------------------------------------------------------
# test_alert_suppressed_incompatible_unit
# ---------------------------------------------------------------------------

def test_alert_suppressed_incompatible_unit():
    """Troponin above threshold with an incompatible unit (mg/dL) must return None."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "mg/dL")
    assert result is None, (
        "Alert must be suppressed when unit is present but incompatible. "
        "mg/dL is not a standard Troponin unit."
    )


def test_alert_suppressed_nondl_variant():
    """ng/dL must be suppressed -- it is NOT a standard Troponin unit per clinical spec."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "ng/dL")
    assert result is None, "ng/dL is excluded from Troponin expected_units by clinical design"


def test_alert_suppressed_incompatible_unit_case_insensitive():
    """Incompatible unit check must also be case-insensitive (MG/DL still suppresses)."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "MG/DL")
    assert result is None, "Case-insensitive mismatch must still suppress the alert"


# ---------------------------------------------------------------------------
# test_alert_fires_missing_unit_backward_compat
# ---------------------------------------------------------------------------

def test_alert_fires_missing_unit_backward_compat_no_arg():
    """Callers that pass no unit argument at all must preserve legacy alert behavior."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH)
    assert result is not None, (
        "Legacy callers that omit unit must still receive alerts (backward-compatible)"
    )


def test_alert_fires_missing_unit_backward_compat_empty_string():
    """Callers that pass unit='' must also preserve legacy alert behavior."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "")
    assert result is not None, (
        "Empty-string unit must preserve legacy behavior (no governance side effect)"
    )


def test_alert_fires_missing_unit_backward_compat_whitespace_only():
    """A unit that is whitespace-only normalizes to empty and must fire."""
    result = check_alert(TROPONIN_CODE, TROPONIN_HIGH, "   ")
    assert result is not None, (
        "Whitespace-only unit normalizes to empty -- must preserve legacy behavior"
    )


# ---------------------------------------------------------------------------
# test_alert_not_triggered_wrong_value_type
# ---------------------------------------------------------------------------

def test_alert_not_triggered_wrong_value_type():
    """Non-numeric value 'POSITIVE' with a correct unit must return None (regression guard)."""
    result = check_alert(TROPONIN_CODE, "POSITIVE", "ng/mL")
    assert result is None, (
        "Non-numeric values must not trigger alerts (regression: float() catch path)"
    )


def test_alert_not_triggered_none_value():
    """None value must return None without raising."""
    result = check_alert(TROPONIN_CODE, None, "ng/mL")
    assert result is None


def test_alert_not_triggered_empty_value():
    """Empty-string value must return None without raising."""
    result = check_alert(TROPONIN_CODE, "", "ng/mL")
    assert result is None


# ---------------------------------------------------------------------------
# test_existing_rules_unaffected
# ---------------------------------------------------------------------------

def test_existing_rules_unaffected_glucose_mg_dl():
    """Glucose (2345-7) above threshold with mg/dL must still fire."""
    result = check_alert(GLUCOSE_CODE, GLUCOSE_HIGH, "mg/dL")
    assert result is not None, "Glucose alert must fire for mg/dL"
    assert result["level"] == "WARNING"


def test_existing_rules_unaffected_glucose_mmol_l():
    """Glucose (2345-7) above threshold with mmol/L must still fire."""
    result = check_alert(GLUCOSE_CODE, GLUCOSE_HIGH, "mmol/L")
    assert result is not None, "Glucose alert must fire for mmol/L"


def test_existing_rules_unaffected_glucose_alt_code():
    """Alternative Glucose code (2339-0) with mg/dL must still fire."""
    result = check_alert(GLUCOSE_ALT_CODE, GLUCOSE_HIGH, "mg/dL")
    assert result is not None, "Alternative Glucose code 2339-0 must fire for mg/dL"


def test_existing_rules_unaffected_glucose_incompatible_unit():
    """Glucose with an incompatible unit must be suppressed."""
    result = check_alert(GLUCOSE_CODE, GLUCOSE_HIGH, "ng/mL")
    assert result is None, "Glucose alert must be suppressed for incompatible unit ng/mL"


def test_existing_rules_unaffected_potassium_meq_l():
    """Potassium (6298-4) above threshold with mEq/L must still fire."""
    result = check_alert(POTASSIUM_CODE, POTASSIUM_HIGH, "mEq/L")
    assert result is not None, "Potassium alert must fire for mEq/L"
    assert result["level"] == "CRITICAL"


def test_existing_rules_unaffected_potassium_mmol_l():
    """Potassium above threshold with mmol/L must still fire."""
    result = check_alert(POTASSIUM_CODE, POTASSIUM_HIGH, "mmol/L")
    assert result is not None, "Potassium alert must fire for mmol/L"


def test_existing_rules_unaffected_potassium_incompatible_unit():
    """Potassium with an incompatible unit must be suppressed."""
    result = check_alert(POTASSIUM_CODE, POTASSIUM_HIGH, "ng/mL")
    assert result is None, "Potassium alert must be suppressed for incompatible unit ng/mL"


def test_existing_rules_unaffected_below_threshold_no_alert():
    """Values below threshold must never fire regardless of unit."""
    result = check_alert(TROPONIN_CODE, 0.01, "ng/mL")
    assert result is None, "Sub-threshold value must not trigger alert"


def test_unknown_code_returns_none():
    """An unrecognized LOINC code must return None regardless of value/unit."""
    result = check_alert("99999-9", 999.0, "mg/dL")
    assert result is None
