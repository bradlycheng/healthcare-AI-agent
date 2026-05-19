# app/patient_timeline.py
"""
Patient Timeline Module
=======================
Provides functions to get patient history and generate AI journey summaries.
"""

from __future__ import annotations

import sqlite3
import os
from typing import Any, Dict, List, Optional

from .llm_gateway import LLMError, patient_summary

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")


def get_unique_patients(db_path: str = DB_PATH) -> List[Dict[str, Any]]:
    """
    Get list of unique patients from the database.
    Returns patient info with visit count.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("""
            SELECT 
                patient_id,
                patient_first_name,
                patient_last_name,
                patient_dob,
                patient_sex,
                COUNT(*) as visit_count,
                MAX(received_at) as last_visit
            FROM hl7_messages
            WHERE patient_id IS NOT NULL AND patient_id != ''
            GROUP BY patient_id
            ORDER BY last_visit DESC
        """).fetchall()
        
        patients = []
        for r in rows:
            patients.append({
                "patient_id": r["patient_id"],
                "first_name": r["patient_first_name"] or "",
                "last_name": r["patient_last_name"] or "",
                "dob": r["patient_dob"] or "",
                "sex": r["patient_sex"] or "",
                "visit_count": r["visit_count"],
                "last_visit": r["last_visit"] or "",
            })
        return patients
    finally:
        conn.close()


def get_patient_timeline(patient_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
    """
    Get full timeline for a patient: all visits with their observations.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Get patient info from most recent message
        patient_row = conn.execute("""
            SELECT 
                patient_id,
                patient_first_name,
                patient_last_name,
                patient_dob,
                patient_sex
            FROM hl7_messages
            WHERE patient_id = ?
            ORDER BY received_at DESC
            LIMIT 1
        """, (patient_id,)).fetchone()
        
        if not patient_row:
            return None
        
        patient_info = {
            "patient_id": patient_row["patient_id"],
            "first_name": patient_row["patient_first_name"] or "",
            "last_name": patient_row["patient_last_name"] or "",
            "dob": patient_row["patient_dob"] or "",
            "sex": patient_row["patient_sex"] or "",
        }
        
        # Get all visits (messages) for this patient
        message_rows = conn.execute("""
            SELECT id, received_at, raw_hl7
            FROM hl7_messages
            WHERE patient_id = ?
            ORDER BY received_at ASC
        """, (patient_id,)).fetchall()
        
        visits = []
        all_observations = []
        
        for msg in message_rows:
            message_id = msg["id"]
            
            # Get observations for this message
            obs_rows = conn.execute("""
                SELECT 
                    code, display, value_num, value_raw, unit,
                    reference_low, reference_high, flag,
                    observation_datetime, status
                FROM observations
                WHERE message_id = ?
                ORDER BY id ASC
            """, (message_id,)).fetchall()
            
            observations = []
            for o in obs_rows:
                value = o["value_num"] if o["value_num"] is not None else o["value_raw"]
                obs = {
                    "code": o["code"] or "",
                    "display": o["display"] or o["code"] or "",
                    "value": value,
                    "unit": o["unit"] or "",
                    "reference_low": o["reference_low"],
                    "reference_high": o["reference_high"],
                    "flag": o["flag"] or "",
                    "observation_datetime": o["observation_datetime"] or "",
                    "status": o["status"] or "",
                }
                observations.append(obs)
                all_observations.append({
                    **obs,
                    "visit_date": msg["received_at"],
                })
            
            visits.append({
                "message_id": message_id,
                "date": msg["received_at"],
                "observations": observations,
            })
        
        return {
            "patient": patient_info,
            "visits": visits,
            "all_observations": all_observations,
            "visit_count": len(visits),
        }
    finally:
        conn.close()


def generate_journey_summary(timeline_data: Dict[str, Any]) -> str:
    """
    Use LLM to generate a patient journey summary based on their history.
    """
    if not timeline_data or not timeline_data.get("visits"):
        return "No visit history available for this patient."
    
    patient = timeline_data["patient"]
    visits = timeline_data["visits"]
    
    # Build a summary of visits for the LLM
    visit_summaries = []
    for v in visits:
        obs_text = ", ".join([
            f"{o['display']}: {o['value']} {o['unit']} ({o['flag']})" 
            for o in v["observations"] if o.get("value")
        ])
        visit_summaries.append(f"- {v['date']}: {obs_text or 'No observations'}")
    
    prompt = f"""You are a clinical assistant. Summarize this patient's healthcare journey.

PATIENT CONTEXT:
Sex: {patient['sex'] or 'unknown'}
Direct identifiers are withheld by governance policy.

VISIT HISTORY:
{chr(10).join(visit_summaries)}

TASK:
1. Identify trends (improving, worsening, stable)
2. Flag any concerning patterns
3. Keep summary to 2-3 sentences

Return ONLY the summary text, no JSON."""

    try:
        # Use a simpler call that returns text
        summary = patient_summary(prompt)
        return summary.strip() if summary else "Unable to generate summary."
    except Exception as e:
        print(f"Journey summary error: {e}")
        return "AI summary temporarily unavailable."
