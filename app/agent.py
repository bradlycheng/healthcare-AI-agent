# app/agent.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .db import init_db, insert_message_and_observations
from .hl7_msh import parse_msh
from .hl7_parser import parse_oru
from .llm_client import LLMError, call_llm_for_json
from .alerts import check_alert

# Toggle this if/when you want to actually use Ollama for enrichment.
USE_LLM = True

# Text-based OBX-2 value types that need AI analysis (per HL7 v2 spec)
TEXT_VALUE_TYPES = {"TX", "FT", "ED", "ST"}


def _needs_ai_analysis(observations: List[Dict[str, Any]]) -> bool:
    """
    Check if message contains clinical notes requiring AI processing.
    """
    for obs in observations:
        notes = obs.get("notes", [])
        if notes and any(n.strip() for n in notes):
            print(f"DEBUG: AI needed due to notes: {notes}")
            return True
        
        vtype = obs.get("value_type", "").upper()
        if vtype in TEXT_VALUE_TYPES:
            print(f"DEBUG: AI needed due to text type: {vtype}")
            return True
    
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flag_to_phrase(flag: str) -> Optional[str]:
    mapping = {"H": "high", "L": "low", "N": "within normal range"}
    return mapping.get((flag or "").strip().upper())


def _hl7_ts_to_iso(ts: str) -> str:
    if not ts or not isinstance(ts, str): return ts
    s = ts.strip()
    if len(s) < 8: return s
    date_part = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 14:
        return f"{date_part}T{s[8:10]}:{s[10:12]}:{s[12:14]}"
    return date_part


def _basic_clinical_summary(structured_observations: List[Dict[str, Any]]) -> str:
    if not structured_observations:
        return "No clinically meaningful observation values were parsed from the HL7 message."
    phrases: List[str] = []
    for ob in structured_observations:
        label = ob.get("display") or ob.get("code") or "observation"
        val = ob.get("value")
        val_str = str(val) if val is not None else "no recorded value"
        unit = ob.get("unit") or ""
        flag_p = _flag_to_phrase(ob.get("flag"))
        if flag_p:
            phrases.append(f"{label} is {flag_p} at {val_str} {unit}.".replace("  ", " "))
        else:
            phrases.append(f"{label} has a value of {val_str} {unit}.".replace("  ", " "))
    return " ".join(phrases)


def _gender_from_sex(sex: str) -> Optional[str]:
    s = (sex or "").strip().upper()
    mapping = {"M": "male", "F": "female", "O": "other", "U": "unknown"}
    return mapping.get(s)


def _dob_to_fhir_date(dob: str) -> Optional[str]:
    s = (dob or "").strip()
    if len(s) < 8: return None
    return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"


def _status_hl7_to_fhir(status: str) -> str:
    s = (status or "").strip().upper()
    if s == "F": return "final"
    if s == "P": return "preliminary"
    return "unknown"


def _build_fhir_bundle(patient: Dict[str, Any], structured_observations: List[Dict[str, Any]]) -> Dict[str, Any]:
    patient_id = patient.get("id") or "patient-1"
    patient_res = {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"family": patient.get("last_name", ""), "given": [patient.get("first_name", "")]}],
        "gender": _gender_from_sex(patient.get("sex")),
        "birthDate": _dob_to_fhir_date(patient.get("dob"))
    }
    entries = [{"fullUrl": f"urn:uuid:{patient_id}", "resource": patient_res}]
    for idx, ob in enumerate(structured_observations, 1):
        code = ob.get("code") or "UNKNOWN"
        display = ob.get("display") or code
        value = ob.get("value")
        obs_res = {
            "resourceType": "Observation",
            "id": f"obs-{idx}",
            "status": _status_hl7_to_fhir(ob.get("status")),
            "code": {"coding": [{"system": "http://loinc.org", "code": code, "display": display}], "text": display},
            "subject": {"reference": f"Patient/{patient_id}"},
            "effectiveDateTime": _hl7_ts_to_iso(ob.get("observation_datetime"))
        }
        if isinstance(value, (int, float)):
            obs_res["valueQuantity"] = {"value": float(value), "unit": ob.get("unit", "")}
        elif value:
            obs_res["valueString"] = str(value)
        entries.append({"fullUrl": f"urn:uuid:obs-{idx}", "resource": obs_res})
    return {"resourceType": "Bundle", "type": "collection", "entry": entries}


def _build_llm_prompt(patient: Dict[str, Any], structured_observations: List[Dict[str, Any]]) -> str:
    import json as _json
    patient_json = _json.dumps(patient, ensure_ascii=False)
    obs_json = _json.dumps(structured_observations, ensure_ascii=False)
    all_notes = []
    for o in structured_observations:
        for n in o.get("notes", []):
            all_notes.append(f"- Note attached to {o.get('display', 'observation')}: {n}")
    notes_block = "CLINICAL NOTES FOUND IN INPUT:\n" + "\n".join(all_notes) if all_notes else "NO NOTES FOUND."

    return f"""
You are a smart clinical assistant. Your PRIMARY goal is to extract clinical values from free-text notes.

INPUT DATA:
---
PATIENT: {patient_json}
---
OBSERVATIONS (Structured): {obs_json}
---
NOTES (Free Text):
{notes_block}

TASK:
1. ANALYZE the "NOTES (Free Text)" section for clinical observations.
2. EXTRACT new quantitative (NUMERIC) findings or UPDATED values.
3. **STRICT NEGATION**: Do NOT extract any value mentioned in a negative context.
   - Example: "BP is not 120/80" -> SKIP.
   - Example: "No fever (102F)" -> SKIP.
4. **REFERENCE VS RESULT**: ONLY extract the patient's result.
   - Example: "Normal range 4-11, current is 6.5" -> Extract 6.5 ONLY.
5. **CATEGORICAL ACCURACY**: Only map values to codes if the text naming the observation matches (e.g., "Pulse" to HR).
6. LOINC REFERENCE:
   - Hemoglobin: "718-7" (g/dL) | WBC: "6690-2" (/uL)
   - BP Systolic: "8480-6" (mmHg) | BP Diastolic: "8462-4" (mmHg)
   - Heart Rate: "8867-4" (bpm) | SpO2: "59408-5" (%)
   - Glucose: "2345-7" (mg/dL) | Temperature: "8310-5" (F)
   - Weight: "29463-7" (kg)

OUTPUT JSON FORMAT:
{{
  "thought_process": "Explain for each candidate if it was POSITIVE (extracted) or NEGATIVE (skipped).",
  "new_observations": [
    {{
      "code": "...", "display": "...", "value": ..., "unit": "...", "source": "AI_EXTRACTED"
    }}
  ]
}}

STRICT CONSTRAINT: Return ONLY valid JSON. No preamble. ONLY include data explicitly stated in the notes.
""".strip()


def _merge_llm_output(base_patient, base_summary, base_structured_obs, base_fhir_bundle, llm_raw) -> Tuple:
    structured_observations = list(base_structured_obs)
    new_obs = llm_raw.get("new_observations", [])
    if isinstance(new_obs, list):
        for o in new_obs:
            if not isinstance(o, dict): continue
            o["source"] = "AI_EXTRACTED"
            # Allow update if value is different
            is_dupe = any(str(b["code"]) == str(o.get("code")) and str(b["value"]) == str(o.get("value")) for b in base_structured_obs)
            if not is_dupe:
                structured_observations.append(o)
    return base_patient, base_summary, structured_observations, base_fhir_bundle


def _ensure_obs_fields(obs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    fixed = []
    for o in obs or []:
        if not isinstance(o, dict): continue
        fixed.append({
            "code": o.get("code", "") or "",
            "display": o.get("display") or o.get("code", "") or "observation",
            "value": o.get("value"),
            "unit": o.get("unit", ""),
            "reference_low": o.get("reference_low"),
            "reference_high": o.get("reference_high"),
            "flag": o.get("flag", ""),
            "observation_datetime": o.get("observation_datetime", ""),
            "status": o.get("status", ""),
            "notes": o.get("notes", []),
            "value_type": o.get("value_type", ""),
            "source": o.get("source", "HL7")
        })
    return fixed

LOINC_LOOKUP = [
    ("diastolic", "8462-4", "mmHg"), ("systolic", "8480-6", "mmHg"),
    ("glucose", "2345-7", "mg/dL"), ("hemoglobin", "718-7", "g/dL"),
    ("wbc", "6690-2", "/uL"), ("heart rate", "8867-4", "bpm"), ("pulse", "8867-4", "bpm"),
    ("spo2", "59408-5", "%"), ("o2 sat", "59408-5", "%")
]

def _normalize_loinc_codes(obs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for o in obs:
        disp = (o.get("display") or "").lower()
        for p, c, u in LOINC_LOOKUP:
            if p in disp:
                o["code"] = c
                if not o.get("unit"): o["unit"] = u
                break
    return obs


def run_oru_pipeline(hl7_text: str, use_llm: bool = True, persist: bool = True) -> Dict[str, Any]:
    try:
        patient, structured_observations = parse_oru(hl7_text)
    except Exception as e:
        raise ValueError(f"Invalid HL7 Message: {e}")

    for ob in structured_observations: ob["source"] = "HL7"
    structured_observations = _ensure_obs_fields(structured_observations)
    clinical_summary = _basic_clinical_summary(structured_observations)
    fhir_bundle = _build_fhir_bundle(patient, structured_observations)

    if USE_LLM and use_llm and _needs_ai_analysis(structured_observations):
        try:
            prompt = _build_llm_prompt(patient, structured_observations)
            llm_raw = call_llm_for_json(prompt)
            patient, clinical_summary, structured_observations, fhir_bundle = _merge_llm_output(
                patient, clinical_summary, structured_observations, fhir_bundle, llm_raw
            )
            structured_observations = _ensure_obs_fields(structured_observations)
            clinical_summary = _basic_clinical_summary(structured_observations)
            fhir_bundle = _build_fhir_bundle(patient, structured_observations)
        except Exception: pass

        structured_observations = _normalize_loinc_codes(structured_observations)
        structured_observations = [o for o in structured_observations if o.get("value") is not None and o.get("value") != ""]

    for ob in structured_observations:
        alert = check_alert(ob.get("code"), ob.get("value"))
        if alert:
            ob["alert_level"], ob["alert_message"] = alert["level"], alert["message"]

    message_id = None
    if persist:
        init_db()
        msh = parse_msh(hl7_text)
        message_id = insert_message_and_observations(
            str(datetime.utcnow()), hl7_text, patient, structured_observations, fhir_bundle, msh.__dict__ if msh else {}
        )

    return {"id": message_id, "patient": patient, "clinical_summary": clinical_summary, "structured_observations": structured_observations, "fhir_bundle": fhir_bundle}
