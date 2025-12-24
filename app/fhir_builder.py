# app/fhir_builder.py

from typing import Any, Dict, List, Optional


def hl7_ts_to_iso(ts: str) -> str:
    """
    Convert a basic HL7 TS (e.g. '20250122090000') to ISO 8601.
    If we can't confidently parse it, just return the original string.
    """
    if not ts:
        return ""

    ts = ts.strip()
    # YYYYMMDDHHMMSS[...]
    if len(ts) >= 14 and ts[:14].isdigit():
        year = ts[0:4]
        month = ts[4:6]
        day = ts[6:8]
        hour = ts[8:10]
        minute = ts[10:12]
        second = ts[12:14]
        rest = ts[14:]
        if rest.startswith("."):
            # keep fractional seconds/timezone tail if present
            return f"{year}-{month}-{day}T{hour}:{minute}:{second}{rest}"
        return f"{year}-{month}-{day}T{hour}:{minute}:{second}"
    # YYYYMMDD
    if len(ts) >= 8 and ts[:8].isdigit():
        year = ts[0:4]
        month = ts[4:6]
        day = ts[6:8]
        return f"{year}-{month}-{day}"

    return ts


def map_gender(hl7_sex: str) -> str:
    """
    Map HL7 administrative sex (M/F/U/etc) to FHIR gender strings.
    """
    sex = (hl7_sex or "").strip().upper()
    if sex == "M":
        return "male"
    if sex == "F":
        return "female"
    if sex in ("O", "OTHER"):
        return "other"
    if sex in ("U", "UNKNOWN"):
        return "unknown"
    return ""


def to_number(value: Any) -> Optional[float]:
    """
    Try to coerce a value into a float.
    Returns None if it can't be parsed.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        return None


def build_patient_resource(patient: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a simple FHIR Patient resource from our parsed patient dict.
    """
    patient_id = patient.get("id") or "patient-1"

    dob_hl7 = patient.get("dob", "")
    birth_date = ""
    iso_dob = hl7_ts_to_iso(dob_hl7)
    if "T" in iso_dob:
        birth_date = iso_dob.split("T", 1)[0]
    else:
        birth_date = iso_dob

    patient_resource: Dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [
            {
                "family": patient.get("last_name", "") or "",
                "given": [patient.get("first_name", "") or ""],
            }
        ],
    }

    if birth_date:
        patient_resource["birthDate"] = birth_date

    gender = map_gender(patient.get("sex", ""))
    if gender:
        patient_resource["gender"] = gender

    return patient_resource


def build_observation_resources(
    patient_id: str,
    structured_observations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build a list of FHIR Observation resources from our structured_observations list.
    """
    obs_resources: List[Dict[str, Any]] = []

    for idx, obs in enumerate(structured_observations, start=1):
        code = obs.get("code") or ""
        display = obs.get("display") or ""
        raw_value = obs.get("value")
        unit = obs.get("unit") or ""
        ref_low_raw = obs.get("reference_low")
        ref_high_raw = obs.get("reference_high")
        flag = (obs.get("flag") or "").strip().upper()
        hl7_ts = obs.get("observation_datetime", "") or ""
        status_raw = (obs.get("status") or "").strip().upper()

        effective_dt = hl7_ts_to_iso(hl7_ts)

        # Normalize status: HL7 OBX-11 'F' -> FHIR 'final'
        if status_raw == "F":
            status = "final"
        elif status_raw:
            status = status_raw.lower()
        else:
            status = "final"

        # Coerce values to numbers where possible
        value_num = to_number(raw_value)
        ref_low_num = to_number(ref_low_raw)
        ref_high_num = to_number(ref_high_raw)

        # Decide valueQuantity vs valueString
        obs_res: Dict[str, Any] = {
            "resourceType": "Observation",
            "id": f"obs-{idx}",
            "status": status,
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",  # placeholder
                        "code": code,
                        "display": display,
                    }
                ],
                "text": display or code,
            },
            "subject": {
                "reference": f"Patient/{patient_id}",
            },
        }

        if value_num is not None:
            value_dict: Dict[str, Any] = {"value": value_num}
            if unit:
                value_dict["unit"] = unit
            obs_res["valueQuantity"] = value_dict
        else:
            obs_res["valueString"] = "" if raw_value is None else str(raw_value)

        if effective_dt:
            obs_res["effectiveDateTime"] = effective_dt

        # Reference range if available
        if ref_low_num is not None or ref_high_num is not None:
            rr: Dict[str, Any] = {}
            if ref_low_num is not None:
                rr.setdefault("low", {})["value"] = ref_low_num
            if ref_high_num is not None:
                rr.setdefault("high", {})["value"] = ref_high_num
            obs_res["referenceRange"] = [rr]

        # Interpretation flag
        if flag in ("H", "L", "N"):
            obs_res["interpretation"] = [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
                            "code": flag,
                        }
                    ]
                }
            ]

        obs_resources.append(obs_res)

    return obs_resources


def build_fhir_bundle(
    patient: Dict[str, Any],
    structured_observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a FHIR Bundle (type=collection) containing:
      - 1 Patient
      - N Observations
    """
    patient_res = build_patient_resource(patient)
    patient_id = patient_res.get("id", "patient-1")

    obs_resources = build_observation_resources(patient_id, structured_observations)

    entries: List[Dict[str, Any]] = []

    entries.append(
        {
            "fullUrl": f"urn:uuid:{patient_id}",
            "resource": patient_res,
        }
    )

    for obs_res in obs_resources:
        obs_id = obs_res.get("id", "")
        entries.append(
            {
                "fullUrl": f"urn:uuid:{obs_id}",
                "resource": obs_res,
            }
        )

    bundle: Dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries,
    }

    return bundle
