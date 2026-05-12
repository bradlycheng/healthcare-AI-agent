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
              FOREIGN KEY(message_id) REFERENCES hl7_messages(id) ON DELETE CASCADE
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

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                ip_address TEXT,
                created_at TEXT
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS governance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT UNIQUE NOT NULL,
                request_id TEXT NOT NULL,
                sequence INTEGER,
                event_type TEXT NOT NULL,
                component TEXT NOT NULL,
                tool_name TEXT,
                decision TEXT,
                reason TEXT,
                model_id TEXT,
                policy_version TEXT,
                success INTEGER,
                row_count INTEGER,
                payload_json TEXT,
                created_at TEXT NOT NULL
            );
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_interactions (
                request_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_question TEXT,
                safe_question TEXT,
                raw_history_json TEXT,
                safe_history_json TEXT,
                plan_json TEXT,
                tool_calls_json TEXT,
                raw_tool_results_json TEXT,
                safe_tool_results_json TEXT,
                final_answer TEXT,
                model_id TEXT,
                tools_used_json TEXT,
                sql_used TEXT,
                row_count INTEGER,
                status TEXT,
                error TEXT
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
            
        try:
            conn.execute("ALTER TABLE observations ADD COLUMN source VARCHAR")
        except sqlite3.OperationalError:
            pass # Column likely exists
            
        conn.commit()
    finally:
        conn.close()


def insert_governance_event(
    request_id: str,
    event_type: str,
    component: str,
    *,
    sequence: int = None,
    tool_name: str = None,
    decision: str = None,
    reason: str = None,
    model_id: str = None,
    policy_version: str = None,
    success: bool = None,
    row_count: int = None,
    payload: Dict[str, Any] = None,
    db_path: str = DB_PATH,
) -> None:
    """Insert a PHI-minimized governance event."""
    import uuid

    conn = get_connection(db_path)
    try:
        conn.execute(
            """
            INSERT INTO governance_events (
                event_id, request_id, sequence, event_type, component,
                tool_name, decision, reason, model_id, policy_version,
                success, row_count, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                request_id,
                sequence,
                event_type,
                component,
                tool_name,
                decision,
                reason,
                model_id,
                policy_version,
                None if success is None else int(bool(success)),
                row_count,
                json.dumps(payload or {}, default=str),
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    except Exception as e:
        print(f"governance_event_write_failed error_type={type(e).__name__}")
    finally:
        conn.close()


def upsert_ai_interaction(
    request_id: str,
    *,
    raw_question: str = None,
    safe_question: str = None,
    raw_history: List[Dict[str, str]] = None,
    safe_history: List[Dict[str, str]] = None,
    plan: Dict[str, Any] = None,
    tool_calls: List[Dict[str, Any]] = None,
    raw_tool_results: List[Dict[str, Any]] = None,
    safe_tool_results: List[Dict[str, Any]] = None,
    final_answer: str = None,
    model_id: str = None,
    tools_used: List[str] = None,
    sql_used: str = None,
    row_count: int = None,
    status: str = None,
    error: str = None,
    db_path: str = DB_PATH,
) -> None:
    """Upsert the protected AI interaction trace for a request.

    This table may contain PHI and should be treated as protected clinical data.
    """
    conn = get_connection(db_path)
    now = datetime.utcnow().isoformat()
    fields = {
        "raw_question": raw_question,
        "safe_question": safe_question,
        "raw_history_json": None if raw_history is None else json.dumps(raw_history, default=str),
        "safe_history_json": None if safe_history is None else json.dumps(safe_history, default=str),
        "plan_json": None if plan is None else json.dumps(plan, default=str),
        "tool_calls_json": None if tool_calls is None else json.dumps(tool_calls, default=str),
        "raw_tool_results_json": None if raw_tool_results is None else json.dumps(raw_tool_results, default=str),
        "safe_tool_results_json": None if safe_tool_results is None else json.dumps(safe_tool_results, default=str),
        "final_answer": final_answer,
        "model_id": model_id,
        "tools_used_json": None if tools_used is None else json.dumps(tools_used, default=str),
        "sql_used": sql_used,
        "row_count": row_count,
        "status": status,
        "error": error,
    }
    active = {k: v for k, v in fields.items() if v is not None}

    try:
        conn.execute(
            """
            INSERT INTO ai_interactions (request_id, created_at, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(request_id) DO NOTHING
            """,
            (request_id, now, now),
        )
        if active:
            assignments = ", ".join([f"{key} = ?" for key in active] + ["updated_at = ?"])
            values = list(active.values()) + [now, request_id]
            conn.execute(
                f"UPDATE ai_interactions SET {assignments} WHERE request_id = ?",
                values,
            )
        conn.commit()
    except Exception as e:
        print(f"ai_interaction_write_failed error_type={type(e).__name__}")
    finally:
        conn.close()


def reconcile_interrupted_ai_interactions(
    older_than_minutes: int = 30,
    db_path: str = DB_PATH,
) -> int:
    """Mark stale non-terminal AI interactions as interrupted.

    This is crash recovery for requests that started but never reached a final
    lifecycle status because the process/container stopped mid-request.
    """
    terminal_statuses = {
        "completed",
        "failed",
        "blocked",
        "completed_legacy",
        "interrupted",
    }
    cutoff = (datetime.utcnow() - timedelta(minutes=older_than_minutes)).isoformat()
    conn = get_connection(db_path)
    reconciled = 0
    event_payloads = []

    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT request_id, status
            FROM ai_interactions
            WHERE updated_at < ?
            """,
            (cutoff,),
        ).fetchall()

        for row in rows:
            request_id = row["request_id"]
            status = row["status"] or ""
            if status in terminal_statuses:
                continue

            now = datetime.utcnow().isoformat()
            cur.execute(
                """
                UPDATE ai_interactions
                SET status = ?, error = ?, updated_at = ?
                WHERE request_id = ?
                """,
                ("interrupted", f"stale_non_terminal_status:{status or 'unknown'}", now, request_id),
            )
            event_payloads.append(
                (request_id, {"previous_status": status or "unknown"})
            )
            reconciled += 1

        conn.commit()
    except Exception as e:
        print(f"ai_interaction_reconcile_failed error_type={type(e).__name__}")
    finally:
        conn.close()

    for request_id, payload in event_payloads:
        insert_governance_event(
            request_id=request_id,
            event_type="request_interrupted_reconciled",
            component="api",
            success=False,
            reason="stale_non_terminal_interaction",
            payload=payload,
            db_path=db_path,
        )

    return reconciled


def save_contact_request(email: str, ip_address: str, db_path: str = DB_PATH) -> bool:
    """
    Save a contact request to the database.
    Enforces a strict limit of 1000 requests to prevent overflow.
    """
    conn = get_connection(db_path)
    try:
        cur = conn.cursor()
        
        # 1. Overflow Protection: Check total count
        count = cur.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        if count >= 1000:
            print("WARNING: Contact table full (1000 limit reached). Rejecting request.")
            return False

        # 2. Insert
        created_at = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO contacts (email, ip_address, created_at) VALUES (?, ?, ?)",
            (email, ip_address, created_at)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"contact_request_save_failed error_type={type(e).__name__}")
        return False
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
    print("delete_all_messages_started", flush=True)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM observations")
        print(f"delete_all_messages_observations count={cur.rowcount}", flush=True)
        cur.execute("DELETE FROM hl7_messages")
        print(f"delete_all_messages_hl7 count={cur.rowcount}", flush=True)
        cur.execute("DELETE FROM visits")
        print(f"delete_all_messages_visits count={cur.rowcount}", flush=True)
        cur.execute("DELETE FROM medications")
        print(f"delete_all_messages_medications count={cur.rowcount}", flush=True)
        cur.execute("DELETE FROM diagnoses")
        print(f"delete_all_messages_diagnoses count={cur.rowcount}", flush=True)
        
        try:
            cur.execute("DELETE FROM contacts")
            print(f"delete_all_messages_contacts count={cur.rowcount}", flush=True)
        except sqlite3.OperationalError:
            print("delete_all_messages_contacts_missing", flush=True)
        
        # Reset sequences for auto-increment IDs
        cur.execute("DELETE FROM sqlite_sequence WHERE name='hl7_messages'")
        cur.execute("DELETE FROM sqlite_sequence WHERE name='observations'")
        cur.execute("DELETE FROM sqlite_sequence WHERE name='medications'")
        cur.execute("DELETE FROM sqlite_sequence WHERE name='diagnoses'")
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name='contacts'")
        except sqlite3.OperationalError:
            pass
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

        # --- STORAGE LIMIT ENFORCEMENT ---
        # Stop saving and raise error if 1300 records reached
        # (Max seed ~1200 + 100 user buffer)
        try:
            count = cur.execute("SELECT COUNT(*) FROM hl7_messages").fetchone()[0]
            if count >= 1300:
                 raise ValueError("Demo database storage limit reached (1300 messages). Please Reset Demo.")
        except ValueError:
            raise
        except Exception as e:
            print(f"storage_limit_check_failed error_type={type(e).__name__}")
        # --------------------------------

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
                  loinc_code,
                  source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    loinc_code,
                    ob.get("source", "HL7")
                ),
            )

        conn.commit()
        return message_id
    finally:
        conn.close()
