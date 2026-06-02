# app/agent.py

from __future__ import annotations

import json as _json
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .db import init_db, insert_message_and_observations
from .hl7_msh import parse_msh
from .hl7_parser import parse_oru
from .llm_gateway import LLMError, hl7_note_extraction
from .alerts import check_alert
from .security import sanitize_text
from .warden import Warden
from .security_validation import IntentGrant, iso_after, new_request_id

# Toggle this if/when you want to actually use AI for enrichment.
USE_LLM = True

# Text-based OBX-2 value types that need AI analysis (per HL7 v2 spec)
TEXT_VALUE_TYPES = {"TX", "FT", "ED", "ST"}


def _needs_ai_analysis(observations: List[Dict[str, Any]]) -> bool:
    """
    Check if message contains clinical notes requiring AI processing.
    """
    for obs in observations:
        notes = obs.get("notes", [])
        vtype = obs.get("value_type", "").upper()
        if notes and any(n.strip() for n in notes):
            return True
        if vtype in TEXT_VALUE_TYPES:
            return True
    return False


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
    all_notes = []
    for o in structured_observations:
        # 1. Include Attached Notes (NTE)
        for n in o.get("notes", []):
            all_notes.append(f"- Note attached to {o.get('display', 'observation')}: {n}")
        
        # 2. Include Text Values (TX, FT, ST)
        vtype = str(o.get("value_type", "")).upper()
        if vtype in TEXT_VALUE_TYPES and o.get("value"):
            all_notes.append(f"- {o.get('display', 'Text Observation')}: {o.get('value')}")

    notes_block = "CLINICAL NOTES FOUND IN INPUT:\n" + "\n".join(all_notes) if all_notes else "NO NOTES FOUND."

    
    json_format_example = """
JSON FORMAT:
{
  "thought_process": "...",
  "new_observations": [
    { "code": "LOINC_OR_CODE", "display": "LABEL", "value": "VALUE_OR_TEXT", "unit": "UNIT_OR_EMPTY" }
  ]
}
"""
    return f"""
<INSTRUCTIONS>
Extract clinical observations, vital signs, symptoms, and diagnoses from the provided notes.
- ONLY extract current, non-negated findings.
- SKIP any value associated with "not", "no", "denies", "none", "negative", "yesterday", "past".
- If a value is not found for a specific metric, DO NOT include it in the output.
- EXTREMELY IMPORTANT: Return VALID JSON only. Do not use placeholders like "(no value)". Use null or strings.

<EXTRACTION_RULES>
1. VITALS: Match to LOINC codes if possible.
   - Heart Rate: 8867-4
   - BP Systolic: 8480-6
   - BP Diastolic: 8462-4
   - Temperature: 8310-5
   - SpO2: 59408-5
   - Resp Rate: 9279-1

2. SYMPTOMS & DIAGNOSES: Extract key findings.
   - Use code "SYMPTOM" for subjective complaints (e.g. Chest Pain, Dizziness).
   - Use code "DIAGNOSIS" for medical impressions (e.g. STEMI, Hypertension).
   - Put the text description in the 'value' field (e.g. value="Chest Pain").
   - Leave 'unit' empty for text findings.

3. MEDICATIONS: Extract new prescriptions.
   - Use code "MED" for medications (e.g. Aspirin).
</EXTRACTION_RULES>

<INPUT_NOTES>
{notes_block}
</INPUT_NOTES>

<OUTPUT_FORMAT>
Return JSON only:
{{
  "thought_process": "brief reasoning",
  "new_observations": [
    {{ "code": "CODE", "display": "LABEL", "value": "VALUE", "unit": "UNIT" }}
  ]
}}
</OUTPUT_FORMAT>
""".strip()



def _merge_llm_output(base_patient, base_summary, base_structured_obs, base_fhir_bundle, llm_raw) -> Tuple:
    if not isinstance(llm_raw, dict):
        return base_patient, base_summary, base_structured_obs, base_fhir_bundle
    
    structured_observations = list(base_structured_obs)
    new_obs = llm_raw.get("new_observations", [])

    if isinstance(new_obs, list):
        for o in new_obs:
            if not isinstance(o, dict): continue
            
            # Ensure required fields
            if not o.get("code") or o.get("value") is None: continue
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
    # Defense in depth: sanitize here as well
    hl7_text = sanitize_text(hl7_text, strict_ascii=True)
    try:
        patient, structured_observations = parse_oru(hl7_text)
    except Exception as e:
        raise ValueError(f"Invalid HL7 Message: {e}")

    for ob in structured_observations: ob["source"] = "HL7"
    structured_observations = _ensure_obs_fields(structured_observations)
    clinical_summary = _basic_clinical_summary(structured_observations)
    fhir_bundle = _build_fhir_bundle(patient, structured_observations)

    llm_raw = {}
    if USE_LLM and use_llm and _needs_ai_analysis(structured_observations):
        try:
            prompt = _build_llm_prompt(patient, structured_observations)

            # Warden IN-GATE: wrap hl7_note_extraction in a request scope so
            # patient PHI in clinical notes is tokenized before reaching the LLM.
            ingestion_grant = IntentGrant(
                intent="hl7_note_extraction",
                risk="medium",
                session_id="hl7_ingestion",
                request_id=new_request_id(),
                scope="hl7_ingestion",
                allowed_tools=[],
                output_fields=["new_observations"],
                max_rows=0,
                expires_at=iso_after(minutes=5),
            )
            warden = Warden()
            with warden.request_scope(grant=ingestion_grant) as warden_ctx:
                # Register new patient identifiers before DB write so first-time
                # patients are tokenized even when not yet in the DB token map.
                warden_ctx.register_identifiers(patient)
                safe_prompt = warden_ctx.anonymize(prompt)

                # Post-anonymize completeness check: verify no raw PHI leaked
                # through the anonymize step before the prompt reaches the LLM.
                _phi_identifiers = [
                    (patient.get("first_name") or "").strip(),
                    (patient.get("last_name") or "").strip(),
                    (f"{(patient.get('first_name') or '').strip()} {(patient.get('last_name') or '').strip()}").strip(),
                    (patient.get("id") or patient.get("patient_id") or "").strip(),
                    (patient.get("dob") or "").strip(),
                ]
                _phi_leaked = any(
                    v and v in safe_prompt for v in _phi_identifiers
                )
                if _phi_leaked:
                    print(
                        "WARDEN: PHI detected in prompt after anonymize -- skipping LLM call",
                        file=sys.stderr, flush=True
                    )
                    llm_raw = {}
                else:
                    llm_raw_result = hl7_note_extraction(safe_prompt)
                    # OUT-GATE: deanonymize string fields that may contain PHI tokens.
                    # Do NOT call anonymize_json() here -- output must be deanonymized,
                    # not re-tokenized.
                    if isinstance(llm_raw_result, dict):
                        llm_raw_str = _json.dumps(llm_raw_result)
                        _deanon_str = warden_ctx.deanonymize(llm_raw_str)
                        llm_raw = _json.loads(_deanon_str)

                        # Post-deanonymize PHI validation: verify LLM output does
                        # not contain raw patient identifiers that bypassed tokenization.
                        _llm_out_str = _json.dumps(llm_raw)
                        _llm_phi_leaked = any(
                            v and v in _llm_out_str for v in _phi_identifiers
                        )
                        if _llm_phi_leaked:
                            print(
                                "WARDEN: PHI detected in LLM output after deanonymize -- discarding",
                                file=sys.stderr, flush=True
                            )
                            llm_raw = {}
                    else:
                        llm_raw = llm_raw_result

            patient, clinical_summary, structured_observations, fhir_bundle = _merge_llm_output(
                patient, clinical_summary, structured_observations, fhir_bundle, llm_raw
            )
            structured_observations = _ensure_obs_fields(structured_observations)
            clinical_summary = _basic_clinical_summary(structured_observations)
            fhir_bundle = _build_fhir_bundle(patient, structured_observations)

            structured_observations = _normalize_loinc_codes(structured_observations)
            structured_observations = [o for o in structured_observations if o.get("value") is not None and o.get("value") != ""]
        except Exception as e:
            print(f"CRITICAL: AI Pipeline Failure: {e}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            pass
    

    for ob in structured_observations:
        alert = check_alert(ob.get("code"), ob.get("value"), ob.get("unit", ""))
        if alert:
            ob["alert_level"], ob["alert_message"] = alert["level"], alert["message"]

    message_id = None
    if persist:
        init_db()
        msh = parse_msh(hl7_text)
        message_id = insert_message_and_observations(
            received_at=str(datetime.utcnow()),
            raw_hl7=hl7_text,
            patient=patient,
            observations=structured_observations,
            fhir_bundle=fhir_bundle,
            msh=msh.__dict__ if msh else {}
        )

    return {
        "id": message_id, 
        "patient": patient, 
        "clinical_summary": clinical_summary, 
        "structured_observations": structured_observations, 
        "fhir_bundle": fhir_bundle,
        "ai_analysis": llm_raw or {}
    }
