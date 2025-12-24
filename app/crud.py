# app/crud.py

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from .models import HL7Message, Observation


def create_hl7_message(
    db: Session,
    *,
    raw_hl7: str,
    patient: Dict[str, Any],
    clinical_summary: Optional[str],
    fhir_bundle_json: Optional[str],
    structured_observations: List[Dict[str, Any]],
) -> HL7Message:
    """
    Persist one HL7 message, patient context, clinical summary,
    FHIR bundle JSON, and all structured observations.
    """
    patient_id = patient.get("id") or None
    first_name = patient.get("first_name") or None
    last_name = patient.get("last_name") or None
    dob = patient.get("dob") or None
    sex = patient.get("sex") or None

    hl7_obj = HL7Message(
        raw_hl7=raw_hl7,
        patient_id=patient_id,
        patient_first_name=first_name,
        patient_last_name=last_name,
        patient_dob=dob,
        patient_sex=sex,
        clinical_summary=clinical_summary or None,
        fhir_bundle_json=fhir_bundle_json or None,
    )

    db.add(hl7_obj)
    db.flush()  # get hl7_obj.id without full commit yet

    for obs in structured_observations:
        value = obs.get("value")
        if isinstance(value, (int, float)):
            value_number = float(value)
            value_text = None
        else:
            value_number = None
            value_text = str(value) if value is not None else None

        db_obs = Observation(
            hl7_message_id=hl7_obj.id,
            code=obs.get("code"),
            display=obs.get("display"),
            value_number=value_number,
            value_text=value_text,
            unit=obs.get("unit"),
            reference_low=obs.get("reference_low"),
            reference_high=obs.get("reference_high"),
            flag=obs.get("flag"),
            observation_datetime=obs.get("observation_datetime"),
            status=obs.get("status"),
        )
        db.add(db_obs)

    db.commit()
    db.refresh(hl7_obj)
    return hl7_obj
