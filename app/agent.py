# app/agent.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .db import init_db, insert_message_and_observations
from .hl7_msh import parse_msh
from .hl7_parser import parse_oru
from .llm_client import LLMError, call_llm_for_json

# Toggle this if/when you want to actually use Ollama for enrichment.
USE_LLM = True

# Text-based OBX-2 value types that need AI analysis (per HL7 v2 spec)
TEXT_VALUE_TYPES = {"TX", "FT", "ED", "ST"}


def _needs_ai_analysis(observations: List[Dict[str, Any]]) -> bool:
    """
    Check if message contains clinical notes requiring AI processing.
    
    Returns True if:
    - Any observation has NTE notes (free-text comments)
    - Any observation has text-based OBX-2 value type (TX, FT, ED, ST)
    
    Returns False for pure numeric data (OBX-2 = NM, SN, CE) which can be
    processed deterministically without LLM.
    """
    for obs in observations:
        # Check for NTE notes attached to observation
        notes = obs.get("notes", [])
        if notes and any(n.strip() for n in notes):
            return True
        
        # Check OBX-2 value type - text types need AI
        vtype = obs.get("value_type", "").upper()
        if vtype in TEXT_VALUE_TYPES:
            return True
    
    return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _flag_to_phrase(flag: str) -> Optional[str]:
    """
    Map HL7 abnormal flags into human phrases.
    H -> "high"
    L -> "low"
    N -> "within normal range"
    """
    flag = (flag or "").strip().upper()
    mapping = {
        "H": "high",
        "L": "low",
        "N": "within normal range",
    }
    return mapping.get(flag)


def _hl7_ts_to_iso(ts: str) -> str:
    """
    Convert basic HL7 TS (YYYYMMDD[HH[MM[SS]]]) into ISO-like formats.

    Examples:
      20250122       -> 2025-01-22
      20250122090000 -> 2025-01-22T09:00:00

    If it doesn't look like a TS, return original.
    """
    if not ts or not isinstance(ts, str):
        return ts

    s = ts.strip()
    if len(s) < 8:
        return s

    date_part = f"{s[0:4]}-{s[4:6]}-{s[6:8]}"

    if len(s) >= 14:
        time_part = f"T{s[8:10]}:{s[10:12]}:{s[12:14]}"
        return date_part + time_part

    return date_part


def _basic_clinical_summary(structured_observations: List[Dict[str, Any]]) -> str:
    """
    Simple deterministic summary using value + abnormal flag.
    This is your fallback when LLM is off or fails.
    """
    if not structured_observations:
        return "No clinically meaningful observation values were parsed from the HL7 message."

    phrases: List[str] = []
    for ob in structured_observations:
        code = (ob.get("code") or "").strip()
        display = (ob.get("display") or "").strip()
        value = ob.get("value")
        unit = (ob.get("unit") or "").strip()
        flag = (ob.get("flag") or "").strip().upper()

        if not display and not code:
            continue

        label = display or code or "observation"
        flag_phrase = _flag_to_phrase(flag)

        if value is None or value == "":
            value_str = "no recorded value"
        else:
            if isinstance(value, float) and value.is_integer():
                value_str = str(int(value))
            else:
                value_str = str(value)

        unit_str = f" {unit}" if unit else ""

        if flag_phrase:
            sentence = f"{label} ({code}) is {flag_phrase} at {value_str}{unit_str}."
        else:
            sentence = f"{label} ({code}) has a value of {value_str}{unit_str}."

        phrases.append(sentence)

    if not phrases:
        return "No clinically meaningful observation values were parsed from the HL7 message."

    return " ".join(phrases)


def _gender_from_sex(sex: str) -> Optional[str]:
    """
    Map HL7 PID-8 (M/F/O/U) to FHIR gender.
    """
    s = (sex or "").strip().upper()
    if s == "M":
        return "male"
    if s == "F":
        return "female"
    if s == "O":
        return "other"
    if s == "U":
        return "unknown"
    return None


def _dob_to_fhir_date(dob: str) -> Optional[str]:
    """
    Convert DOB from HL7 like '19800101' into '1980-01-01'.
    If malformed, return None.
    """
    s = (dob or "").strip()
    if len(s) < 8:
        return None
    try:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    except Exception:
        return None


def _status_hl7_to_fhir(status: str) -> str:
    """
    Map HL7 OBX-11 statuses to FHIR Observation.status.
    Common HL7 values:
      F -> final
      P -> preliminary
    """
    s = (status or "").strip().upper()
    if s == "F":
        return "final"
    if s == "P":
        return "preliminary"
    return "unknown"


def _build_fhir_bundle(
    patient: Dict[str, Any],
    structured_observations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a minimal FHIR Bundle with one Patient + multiple Observations.
    """
    patient_id = patient.get("id") or "patient-1"

    family = (patient.get("last_name") or "").strip()
    given = (patient.get("first_name") or "").strip()
    sex = patient.get("sex") or ""
    dob = patient.get("dob") or ""

    gender = _gender_from_sex(sex)
    birth_date = _dob_to_fhir_date(dob)

    patient_res: Dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
    }

    name_block: Dict[str, Any] = {}
    if family:
        name_block["family"] = family
    if given:
        name_block["given"] = [given]

    if name_block:
        patient_res["name"] = [name_block]

    if birth_date:
        patient_res["birthDate"] = birth_date

    if gender:
        patient_res["gender"] = gender

    bundle_entries: List[Dict[str, Any]] = [
        {
            "fullUrl": f"urn:uuid:{patient_id}",
            "resource": patient_res,
        }
    ]

    for idx, ob in enumerate(structured_observations, start=1):
        code = (ob.get("code") or "").strip() or "UNKNOWN"
        display = (ob.get("display") or "").strip() or code
        value = ob.get("value")
        unit = (ob.get("unit") or "").strip()

        status_fhir = _status_hl7_to_fhir(ob.get("status"))
        obs_dt_raw = ob.get("observation_datetime") or ""
        effective_dt = _hl7_ts_to_iso(obs_dt_raw) if obs_dt_raw else None

        ref_low = ob.get("reference_low")
        ref_high = ob.get("reference_high")
        flag = (ob.get("flag") or "").strip().upper()

        obs_res: Dict[str, Any] = {
            "resourceType": "Observation",
            "id": f"obs-{idx}",
            "status": status_fhir,
            "code": {
                "coding": [
                    {
                        "system": "http://loinc.org",
                        "code": code,
                        "display": display,
                    }
                ],
                "text": display,
            },
            "subject": {
                "reference": f"Patient/{patient_id}",
            },
        }

        if isinstance(value, (int, float)):
            obs_res["valueQuantity"] = {"value": float(value)}
            if unit:
                obs_res["valueQuantity"]["unit"] = unit
        elif value is not None and value != "":
            obs_res["valueString"] = str(value)

        if effective_dt:
            obs_res["effectiveDateTime"] = effective_dt

        if ref_low is not None or ref_high is not None:
            rr: Dict[str, Any] = {}
            if ref_low is not None:
                try:
                    rr["low"] = {"value": float(ref_low)}
                except ValueError:
                    rr["low"] = {"value": ref_low}
            if ref_high is not None:
                try:
                    rr["high"] = {"value": float(ref_high)}
                except ValueError:
                    rr["high"] = {"value": ref_high}
            obs_res["referenceRange"] = [rr]

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

        bundle_entries.append(
            {"fullUrl": f"urn:uuid:obs-{idx}", "resource": obs_res}
        )

    return {"resourceType": "Bundle", "type": "collection", "entry": bundle_entries}


def _build_llm_prompt(
    patient: Dict[str, Any],
    structured_observations: List[Dict[str, Any]],
) -> str:
    import json as _json

    patient_json = _json.dumps(patient, indent=2)
    obs_json = _json.dumps(structured_observations, indent=2)
    
    # Extract all notes for explicit prompting
    all_notes = []
    for o in structured_observations:
        if "notes" in o and o["notes"]:
            for n in o["notes"]:
                all_notes.append(f"- Note attached to {o.get('display', 'observation')}: {n}")
    
    notes_block = ""
    if all_notes:
        notes_block = "CLINICAL NOTES FOUND IN INPUT:\n" + "\n".join(all_notes) + "\n\n"


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
Return a SINGLE JSON object with ALL of the following keys

LOINC CODE REFERENCE (use these exact codes for extracted observations):
- Glucose: code="2345-7", unit="mg/dL"
- Hemoglobin: code="718-7", unit="g/dL"
- WBC: code="6690-2", unit="/uL"
- Blood Pressure Systolic: code="8480-6", unit="mmHg"
- Blood Pressure Diastolic: code="8462-4", unit="mmHg"
- Heart Rate: code="8867-4", unit="bpm"

INSTRUCTIONS:
1. Start with the "OBSERVATIONS (Structured)" list effectively.
2. CHECK the "NOTES (Free Text)" section carefully.
   - If you see a quantitative test result in the notes (like "glucose 145", "BP 120/80") that is NOT in the structured list, you MUST extract it.
   - **IMPORTANT: Even if the note says "Patient reports", TREAT THIS AS A VALID FINDING for this extraction.**
   - Example matches: "patient reports glucose 145", "fasting blood glucose of 145", "last visit glucose 145".
   - **NAMING CONVENTION**: Use standard, concise display names (e.g., use "Glucose" instead of "Fasting Blood Glucose" if possible, or "Blood Pressure" instead of "BP").
   - For extracted items, set "source": "AI_EXTRACTED".
   - For original items, set "source": "HL7".
   - **CRITICALLY IMPORTANT**: You MUST add these new extracted observations to the "structured_observations" list in your JSON output. Do not just put them in the FHIR bundle.
3. Generate a "clinical_summary" of the findings.
4. Generate a valid "fhir_bundle".

OUTPUT JSON FORMAT:
{{
  "patient": {{...}},
  "clinical_summary": "...",
  "notes_analysis": "EXTRACTED: [Value] from [Snippet] | SKIPPED: [Reason]",
  "structured_observations": [
    {{
      "code": "...",
      "display": "...",
      "value": ...,
      "unit": "...",
      "flag": "...",
      "source": "HL7" | "AI_EXTRACTED"
    }}
  ],
  "fhir_bundle": {{...}}
}}

Return ONLY valid JSON.
""".strip()


def _merge_llm_output(
    base_patient: Dict[str, Any],
    base_summary: str,
    base_structured_obs: List[Dict[str, Any]],
    base_fhir_bundle: Dict[str, Any],
    llm_raw: Dict[str, Any],
) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]], Dict[str, Any]]:
    patient = base_patient
    summary = base_summary
    structured_observations = base_structured_obs
    fhir_bundle = base_fhir_bundle

    if isinstance(llm_raw.get("patient"), dict):
        patient = llm_raw["patient"]

    if isinstance(llm_raw.get("clinical_summary"), str):
        summary = llm_raw["clinical_summary"]

    if isinstance(llm_raw.get("structured_observations"), list):
        # The LLM returns the FULL list (merged), so we trust its deduplication logic
        structured_observations = llm_raw["structured_observations"]

    if isinstance(llm_raw.get("fhir_bundle"), dict):
        fhir_bundle = llm_raw["fhir_bundle"]

    return patient, summary, structured_observations, fhir_bundle


def _ensure_obs_fields(obs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Some LLM outputs drop required keys. Normalize so downstream API/DB never crashes.
    """
    fixed: List[Dict[str, Any]] = []
    for o in obs or []:
        if not isinstance(o, dict):
            continue
        fixed.append(
            {
                "code": o.get("code", "") or "",
                "display": o.get("display", "") or o.get("code", "") or "",
                "value": o.get("value"),
                "unit": o.get("unit", "") or "",
                "reference_low": o.get("reference_low"),
                "reference_high": o.get("reference_high"),
                "flag": o.get("flag", "") or "",
                "observation_datetime": o.get("observation_datetime", "") or "",
                "status": o.get("status", "") or "",
                "source": o.get("source", "HL7"),  # Default source
            }
        )
    return fixed


# LOINC code normalization - order matters (more specific patterns first)
LOINC_LOOKUP = [
    ("diastolic", "8462-4", "mmHg"),
    ("systolic", "8480-6", "mmHg"),
    ("blood pressure", "8480-6", "mmHg"),
    ("glucose", "2345-7", "mg/dL"),
    ("hemoglobin", "718-7", "g/dL"),
    ("wbc", "6690-2", "/uL"),
    ("white blood cell", "6690-2", "/uL"),
    ("heart rate", "8867-4", "bpm"),
    ("pulse", "8867-4", "bpm"),
    ("creatinine", "2160-0", "mg/dL"),
]


def _normalize_loinc_codes(obs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize LOINC codes and units for known observation types."""
    normalized = []
    for o in obs:
        display = (o.get("display") or "").lower()
        for pattern, loinc_code, default_unit in LOINC_LOOKUP:
            if pattern in display:
                if o.get("code") != loinc_code:
                    o["code"] = loinc_code
                if not o.get("unit"):
                    o["unit"] = default_unit
                break
        normalized.append(o)
    return normalized


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_oru_pipeline(hl7_text: str, use_llm: bool = True, persist: bool = True) -> Dict[str, Any]:
    print(f"DEBUG: Entering run_oru_pipeline. use_llm={use_llm}, USE_LLM={USE_LLM}", flush=True)
    """
    Main pipeline:

    1. parse_oru -> (patient, structured_observations)
    2. deterministic clinical summary
    3. build local FHIR Bundle
    4. (optional) call local LLM to refine / enrich / extract from notes
    5. (optional) persist to sqlite (preview mode skips this)
    """
    # 1) HL7 -> patient + observations
    patient, structured_observations = parse_oru(hl7_text)
    print(f"DEBUG: Parsed observations: {structured_observations}", flush=True)
    
    # Pre-mark HL7 source
    for ob in structured_observations:
        ob["source"] = "HL7"
        
    structured_observations = _ensure_obs_fields(structured_observations)

    # 2) Local summary
    clinical_summary = _basic_clinical_summary(structured_observations)

    # 3) Local FHIR Bundle
    fhir_bundle = _build_fhir_bundle(patient, structured_observations)

    # 4) Optional LLM enrichment - only when clinical notes are present
    needs_ai = _needs_ai_analysis(structured_observations)
    
    if USE_LLM and use_llm and needs_ai:
        print("DEBUG: Clinical notes detected (NTE or TX/FT values), using LLM", flush=True)
        try:
            prompt = _build_llm_prompt(patient, structured_observations)
            llm_raw = call_llm_for_json(prompt)
            print(f"DEBUG LLM RAW: {llm_raw}")

            patient, clinical_summary, structured_observations, fhir_bundle = _merge_llm_output(
                patient,
                clinical_summary,
                structured_observations,
                fhir_bundle,
                llm_raw,
            )
            structured_observations = _ensure_obs_fields(structured_observations)
        except LLMError as e:
            print(f"DEBUG LLM ERROR: {e}")
            pass
        except Exception as e:
            print(f"DEBUG UNEXPECTED ERROR: {e}")
            pass

        # Post-processing: If AI extracted meaningful values, hide the raw "Clinical Note" to avoid clutter
        ai_extracted_count = sum(1 for o in structured_observations if o.get("source") == "AI_EXTRACTED")
        if ai_extracted_count > 0:
            # Filter out generic notes
            structured_observations = [
                o for o in structured_observations 
                if not (o.get("code") == "NOTE" or o.get("display") == "Clinical Note")
            ]
        
        # Normalize LOINC codes and units
        structured_observations = _normalize_loinc_codes(structured_observations)
        
        # Filter out AI-generated observations with blank values (bad AI output)
        structured_observations = [
            o for o in structured_observations
            if not (o.get("source") == "AI_EXTRACTED" and (o.get("value") == "" or o.get("value") is None))
        ]
        
        # Regenerate FHIR bundle with corrected codes
        fhir_bundle = _build_fhir_bundle(patient, structured_observations)
    elif USE_LLM and use_llm:
        print("DEBUG: Structured numeric data only, skipping LLM for faster processing", flush=True)

    # 5) Persist (Optional)
    if persist:
        try:
            init_db()
            msh_obj = parse_msh(hl7_text)
            msh_dict = msh_obj.__dict__ if msh_obj else {}
            insert_message_and_observations(
                received_at=str(datetime.utcnow()),
                raw_hl7=hl7_text,
                patient=patient,
                observations=structured_observations,
                fhir_bundle=fhir_bundle,
                msh=msh_dict,
            )
        except Exception:
            pass

    return {
        "patient": patient,
        "clinical_summary": clinical_summary,
        "structured_observations": structured_observations,
        "fhir_bundle": fhir_bundle,
    }
