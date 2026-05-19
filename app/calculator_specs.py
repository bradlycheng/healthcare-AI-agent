from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


BLOCKED_CALCULATOR_KEYS = {
    "code",
    "custom_formula",
    "dob",
    "expression",
    "fhir",
    "formula",
    "hl7",
    "identifier",
    "identifiers",
    "medical_record_number",
    "mrn",
    "note",
    "notes",
    "patient",
    "patient_dob",
    "patient_id",
    "patient_name",
    "raw_hl7",
    "raw_row",
    "raw_rows",
    "record",
    "row",
    "rows",
    "sql",
}


@dataclass(frozen=True)
class CalculatorFieldSpec:
    field_type: str
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    allowed_values: Tuple[str, ...] = ()
    unit: str = ""


@dataclass(frozen=True)
class CalculatorSpec:
    name: str
    display_name: str
    required_fields: Mapping[str, CalculatorFieldSpec]
    output_shape: Mapping[str, str]
    formula_id: str
    evidence_note: str = "Hard-coded clinical calculator spec; custom formulas are not accepted."


@dataclass(frozen=True)
class CalculatorValidationResult:
    allowed: bool
    reason: str
    spec_name: Optional[str] = None
    normalized_values: Dict[str, Any] = field(default_factory=dict)
    output_shape: Dict[str, str] = field(default_factory=dict)
    accepted_fields: Tuple[str, ...] = ()


CALCULATOR_SPECS: Dict[str, CalculatorSpec] = {
    "bmi": CalculatorSpec(
        name="bmi",
        display_name="Body Mass Index",
        required_fields={
            "weight_kg": CalculatorFieldSpec("number", minimum=1.0, maximum=400.0, unit="kg"),
            "height_m": CalculatorFieldSpec("number", minimum=0.3, maximum=2.8, unit="m"),
        },
        output_shape={
            "calculation": "str",
            "result": "number",
            "unit": "str",
            "interpretation": "str",
            "formula_id": "str",
        },
        formula_id="bmi_weight_kg_height_m_v1",
    ),
    "egfr": CalculatorSpec(
        name="egfr",
        display_name="eGFR CKD-EPI 2021",
        required_fields={
            "creatinine": CalculatorFieldSpec("number", minimum=0.1, maximum=20.0, unit="mg/dL"),
            "age": CalculatorFieldSpec("integer", minimum=18, maximum=120, unit="years"),
            "sex": CalculatorFieldSpec("enum", allowed_values=("F", "M")),
        },
        output_shape={
            "calculation": "str",
            "result": "number",
            "unit": "str",
            "interpretation": "str",
            "formula_id": "str",
        },
        formula_id="ckd_epi_2021_creatinine_v1",
    ),
}


def get_calculator_spec(calculation: str) -> Optional[CalculatorSpec]:
    return CALCULATOR_SPECS.get((calculation or "").strip().lower())


def validate_calculator_request(tool_input: Mapping[str, Any]) -> CalculatorValidationResult:
    if not isinstance(tool_input, Mapping):
        return _deny("calculator request must be an object")

    top_level_keys = set(tool_input.keys())
    expected_top_level = {"calculation", "values"}
    blocked = _blocked_keys(top_level_keys)
    if blocked:
        return _deny(f"blocked calculator key: {blocked[0]}")

    extras = sorted(top_level_keys - expected_top_level)
    if extras:
        return _deny(f"unexpected calculator field: {extras[0]}")

    calculation = tool_input.get("calculation")
    if not isinstance(calculation, str):
        return _deny("calculation must be a string")

    spec = get_calculator_spec(calculation)
    if spec is None:
        return _deny(f"unsupported calculator: {calculation}")

    values = tool_input.get("values")
    if not isinstance(values, Mapping):
        return _deny("values must be an object")

    value_keys = set(values.keys())
    blocked = _blocked_keys(value_keys)
    if blocked:
        return _deny(f"blocked calculator value: {blocked[0]}")

    allowed_keys = set(spec.required_fields.keys())
    extra_values = sorted(value_keys - allowed_keys)
    if extra_values:
        return _deny(f"unexpected calculator value: {extra_values[0]}")

    missing = sorted(allowed_keys - value_keys)
    if missing:
        return _deny(f"missing calculator value: {missing[0]}")

    normalized: Dict[str, Any] = {}
    for key, field_spec in spec.required_fields.items():
        ok, normalized_value, reason = _validate_field(key, values[key], field_spec)
        if not ok:
            return _deny(reason)
        normalized[key] = normalized_value

    return CalculatorValidationResult(
        allowed=True,
        reason="calculator request matches hard-coded spec",
        spec_name=spec.name,
        normalized_values=normalized,
        output_shape=dict(spec.output_shape),
        accepted_fields=tuple(spec.required_fields.keys()),
    )


def _blocked_keys(keys: set[str]) -> Tuple[str, ...]:
    return tuple(sorted(key for key in keys if key.lower() in BLOCKED_CALCULATOR_KEYS))


def _validate_field(
    key: str,
    value: Any,
    field_spec: CalculatorFieldSpec,
) -> Tuple[bool, Any, str]:
    if field_spec.field_type == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False, None, f"{key} must be a number"
        numeric = float(value)
        return _validate_range(key, numeric, field_spec)

    if field_spec.field_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            return False, None, f"{key} must be an integer"
        return _validate_range(key, value, field_spec)

    if field_spec.field_type == "enum":
        if not isinstance(value, str):
            return False, None, f"{key} must be a string"
        normalized = value.strip().upper()
        if normalized not in field_spec.allowed_values:
            return False, None, f"{key} must be one of {', '.join(field_spec.allowed_values)}"
        return True, normalized, ""

    return False, None, f"{key} has unsupported field type"


def _validate_range(
    key: str,
    value: float,
    field_spec: CalculatorFieldSpec,
) -> Tuple[bool, Any, str]:
    if field_spec.minimum is not None and value < field_spec.minimum:
        return False, None, f"{key} below allowed range"
    if field_spec.maximum is not None and value > field_spec.maximum:
        return False, None, f"{key} above allowed range"
    return True, value, ""


def _deny(reason: str) -> CalculatorValidationResult:
    return CalculatorValidationResult(allowed=False, reason=reason)
