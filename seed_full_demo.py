
import sqlite3
import datetime
import uuid
import os

DB_PATH = "agent.db"

def seed_demo_data():
    # Force delete DB
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
            print(f"Deleted existing DB at {DB_PATH}")
        except PermissionError:
            print("ERROR: Could not delete DB. File might be locked.")
            return

    # Ensure directory (no longer needed for current dir but kept for safety)
    # os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    print(f"Initializing and seeding {DB_PATH}...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Init Schema with received_at
    cursor.execute('''
        CREATE TABLE hl7_messages (
            id TEXT PRIMARY KEY,
            message_type TEXT,
            received_at TEXT,
            patient_id TEXT,
            patient_first_name TEXT,
            patient_last_name TEXT,
            patient_dob TEXT,
            patient_sex TEXT,
            message_datetime TEXT,
            raw_hl7 TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE observations (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            code TEXT,
            display TEXT,
            value_num REAL,
            value_raw TEXT,
            unit TEXT,
            reference_low TEXT,
            reference_high TEXT,
            flag TEXT,
            observation_datetime TEXT,
            status TEXT,
            FOREIGN KEY(message_id) REFERENCES hl7_messages(id)
        )
    ''')
    
    # Verify Schema
    cursor.execute("PRAGMA table_info(hl7_messages)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"Columns in hl7_messages: {columns}")
    if "received_at" not in columns:
        print("CRITICAL ERROR: received_at column missing!")
        return

    # ---------------------------------------------------------
    # 1. Sarah Jenkins (Hypertension)
    # ---------------------------------------------------------
    print("Seeding Sarah Jenkins (Hypertension)...")
    sarah_id = str(uuid.uuid4())
    dt_sarah = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO hl7_messages (id, message_type, received_at, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, message_datetime, raw_hl7)
        VALUES (?, 'ORU^R01', ?, 'P-SARAH', 'SARAH', 'JENKINS', '1980-05-15', 'F', ?, 'SEED_SARAH')
    """, (sarah_id, dt_sarah, dt_sarah))
    
    # High BP Obsevations
    cursor.execute("""
        INSERT INTO observations (id, message_id, code, display, value_num, unit, flag, observation_datetime, status)
        VALUES 
        (?, ?, '8480-6', 'Systolic Blood Pressure', 150, 'mmHg', 'H', ?, 'F'),
        (?, ?, '8462-4', 'Diastolic Blood Pressure', 95, 'mmHg', 'H', ?, 'F')
    """, (str(uuid.uuid4()), sarah_id, dt_sarah, str(uuid.uuid4()), sarah_id, dt_sarah))

    # ---------------------------------------------------------
    # 2. John Smith (Diabetes)
    # ---------------------------------------------------------
    print("Seeding John Smith (Diabetes)...")
    john_id = str(uuid.uuid4())
    dt_john = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO hl7_messages (id, message_type, received_at, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, message_datetime, raw_hl7)
        VALUES (?, 'ORU^R01', ?, 'P-JOHN', 'JOHN', 'SMITH', '1964-05-15', 'M', ?, 'SEED_JOHN')
    """, (john_id, dt_john, dt_john))
    
    # High Glucose and A1c
    cursor.execute("""
        INSERT INTO observations (id, message_id, code, display, value_num, unit, flag, observation_datetime, status)
        VALUES 
        (?, ?, '15074-8', 'Glucose [Mass/volume] in Blood', 250, 'mg/dL', 'H', ?, 'F'),
        (?, ?, '4548-4', 'Hemoglobin A1c/Hemoglobin.total', 9.5, '%', 'H', ?, 'F')
    """, (str(uuid.uuid4()), john_id, dt_john, str(uuid.uuid4()), john_id, dt_john))

    conn.commit()
    conn.close()
    print("Seeding Complete: Sarah Jenkins (HTN) & John Smith (DM)")

if __name__ == "__main__":
    seed_demo_data()
