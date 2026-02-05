# app/db.py

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional

import os

DB_PATH = os.getenv("DATABASE_PATH", "agent.db")

# Thread-local storage for connections
_local = threading.local()


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """
    Get a database connection with proper settings for concurrent access.
    Uses WAL mode for better concurrent read/write handling.
    """
    conn = sqlite3.connect(db_path, timeout=30.0)
    
    # Enable WAL mode for better concurrency (allows reads during writes)
    conn.execute("PRAGMA journal_mode=WAL")
    
    # Set busy timeout to wait instead of immediately failing on lock
    conn.execute("PRAGMA busy_timeout=5000")
    
    # Synchronous mode - NORMAL is good balance of safety and speed
    conn.execute("PRAGMA synchronous=NORMAL")
    
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys=ON")
    
    # Use Row factory for name-based access
    conn.row_factory = sqlite3.Row
    
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    """
    Create tables if they don't exist.
    Matches the schema you showed:
      hl7_messages(received_at, raw_hl7, patient_*, fhir_bundle_json)
      observations(message_id, code, display, value_num/value_raw, unit, ref range, flag, obs dt, status)
    """
    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hl7_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              received_at DATETIME,
              raw_hl7 TEXT,
              patient_id VARCHAR,
              patient_first_name VARCHAR,
              patient_last_name VARCHAR,
              patient_dob VARCHAR,
              patient_sex VARCHAR,
              fhir_bundle_json TEXT
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS observations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              message_id INTEGER,
              code VARCHAR,
              display VARCHAR,
              value_num FLOAT,
              value_raw VARCHAR,
              unit VARCHAR,
              reference_low VARCHAR,
              reference_high VARCHAR,
              flag VARCHAR,
              observation_datetime VARCHAR,
              status VARCHAR,
              alert_level VARCHAR,
              alert_message VARCHAR,
              loinc_code VARCHAR,
              FOREIGN KEY(message_id) REFERENCES hl7_messages(id)
            );
            """
        )
        
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visits (
                visit_id TEXT PRIMARY KEY,
                patient_id TEXT,
                visit_date TEXT,
                visit_type TEXT,
                provider_name TEXT,
                chief_complaint TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT,
                medication_name TEXT,
                dosage TEXT,
                frequency TEXT,
                start_date TEXT,
                end_date TEXT,
                status TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT,
                diagnosis_code TEXT,
                diagnosis_name TEXT,
                diagnosis_date TEXT,
                status TEXT
            );
            """
        )
        
        # Migration for existing tables
        try:
            conn.execute("ALTER TABLE observations ADD COLUMN alert_level VARCHAR")
        except sqlite3.OperationalError:
            pass # Column likely exists
            
        try:
            conn.execute("ALTER TABLE observations ADD COLUMN alert_message VARCHAR")
        except sqlite3.OperationalError:
            pass # Column likely exists

        try:
            conn.execute("ALTER TABLE observations ADD COLUMN loinc_code VARCHAR")
        except sqlite3.OperationalError:
            pass # Column likely exists
            
        conn.commit()
    finally:
        conn.close()


def prune_messages(days_to_keep: int = 2, db_path: str = DB_PATH) -> int:
    """
    Delete messages and observations older than `days_to_keep`.
    Returns the number of messages deleted.
    """
    conn = get_connection(db_path)
    try:
        # Calculate retention cutoff
        cutoff = (datetime.utcnow() - timedelta(days=days_to_keep)).isoformat()
        
        # 1. Find IDs to delete
        cur = conn.cursor()
        cur.execute("SELECT id FROM hl7_messages WHERE received_at < ?", (cutoff,))
        rows = cur.fetchall()
        if not rows:
            return 0
        
        ids_to_delete = [str(r[0]) for r in rows]
        id_list_str = ",".join(ids_to_delete)
        
        # 2. Delete observations (if cascading delete isn't enabled)
        if id_list_str:
             cur.execute(f"DELETE FROM observations WHERE message_id IN ({id_list_str})")
             # 3. Delete messages
             cur.execute(f"DELETE FROM hl7_messages WHERE id IN ({id_list_str})")
        
        conn.commit()
        return len(ids_to_delete)
    finally:
        conn.close()


def delete_all_messages(db_path: str = DB_PATH) -> None:
    """
    Clear all data from the database.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM observations")
        cur.execute("DELETE FROM hl7_messages")
        conn.commit()
    finally:
        conn.close()


def _split_ref_range(ref_range: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    HL7 OBX-7 often comes like '70-110' or '3.5-5.1'.
    If we already have separate reference_low/high, you won't call this.
    """
    if not ref_range:
        return None, None
    s = str(ref_range).strip()
    if "-" not in s:
        return None, None
    lo, hi = s.split("-", 1)
    lo = lo.strip() or None
    hi = hi.strip() or None
    return lo, hi


def _coerce_value(value: Any) -> Tuple[Optional[float], Optional[str]]:
    """
    Store numeric values in value_num when possible, else store in value_raw.
    """
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    s = str(value).strip()
    if s == "":
        return None, ""
    try:
        return float(s), None
    except ValueError:
        return None, s

def insert_message_and_observations(
    raw_hl7: str = "",
    patient: Dict[str, Any] = None,
    observations: List[Dict[str, Any]] = None,
    fhir_bundle: Dict[str, Any] = None,
    db_path: str = DB_PATH,
    received_at: str = None,
    msh: Dict[str, Any] = None,
    # Legacy parameter names for backwards compatibility
    hl7_text: str = None,
    structured_observations: List[Dict[str, Any]] = None,
) -> int:
    """
    Inserts into hl7_messages + observations. Returns new message_id.
    """
    # Handle legacy parameter names
    if hl7_text is not None and not raw_hl7:
        raw_hl7 = hl7_text
    if structured_observations is not None and observations is None:
        observations = structured_observations
    if patient is None:
        patient = {}
    if observations is None:
        observations = []
    if fhir_bundle is None:
        fhir_bundle = {}
    
    conn = get_connection(db_path)
    try:
        if received_at is None:
            received_at = datetime.utcnow().isoformat(sep=" ", timespec="microseconds")

        pid = str(patient.get("id") or "")
        first = str(patient.get("first_name") or "")
        last = str(patient.get("last_name") or "")
        dob = str(patient.get("dob") or "")
        sex = str(patient.get("sex") or "")

        bundle_json = json.dumps(fhir_bundle)

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO hl7_messages (
              received_at,
              raw_hl7,
              patient_id,
              patient_first_name,
              patient_last_name,
              patient_dob,
              patient_sex,
              fhir_bundle_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (received_at, raw_hl7, pid, first, last, dob, sex, bundle_json),
        )
        message_id = int(cur.lastrowid)

        for ob in observations or []:
            code = str(ob.get("code") or "")
            display = str(ob.get("display") or code or "")
            unit = str(ob.get("unit") or "")
            flag = str(ob.get("flag") or "")
            obs_dt = str(ob.get("observation_datetime") or "")
            status = str(ob.get("status") or "")
            alert_level = str(ob.get("alert_level") or "")
            alert_msg = str(ob.get("alert_message") or "")
            if alert_level:
                print(f"DEBUG DB INSERT OBSERVATION: Code={code}, AlertLevel={alert_level}", flush=True)

            # Prefer explicit reference_low/high if provided; else try splitting a combined range (if any)
            ref_low = ob.get("reference_low")
            ref_high = ob.get("reference_high")
            if (ref_low is None or ref_low == "") and (ref_high is None or ref_high == ""):
                # Some parsers put ref range into a single field; safe no-op if not present
                lo, hi = _split_ref_range(ob.get("reference_range"))  # optional key
                ref_low = ref_low or lo
                ref_high = ref_high or hi

            value_num, value_raw = _coerce_value(ob.get("value"))

            loinc_code = str(ob.get("loinc_code") or "")

            cur.execute(
                """
                INSERT INTO observations (
                  message_id,
                  code,
                  display,
                  value_num,
                  value_raw,
                  unit,
                  reference_low,
                  reference_high,
                  flag,
                  observation_datetime,
                  status,
                  alert_level,
                  alert_message,
                  loinc_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    code,
                    display,
                    value_num,
                    value_raw,
                    unit,
                    None if ref_low is None else str(ref_low),
                    None if ref_high is None else str(ref_high),
                    flag,
                    obs_dt,
                    status,
                    alert_level,
                    alert_msg,
                    loinc_code
                ),
            )

        conn.commit()
        return message_id
    finally:
        conn.close()
