
import sqlite3
import uuid
from datetime import datetime, timedelta
import random

DB_PATH = "agent.db"

def seed_vitals_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create a consistent patient
    patient_id = "VITALS-TEST-001"
    first_name = "Timeline"
    last_name = "Tester"
    dob = "19800101"
    sex = "M"
    
    # Generate 5 visits over the last 5 months
    base_date = datetime.now() - timedelta(days=150)
    
    print(f"Seeding history for patient: {first_name} {last_name} ({patient_id})")
    
    for i in range(5):
        visit_date = base_date + timedelta(days=i*30)
        visit_date_str = visit_date.strftime("%Y%m%d%H%M%S")
        
        # Simulated trend: BP improving (dropping), HR stable
        sys_bp = 150 - (i * 5) + random.randint(-2, 2)  # Starts 150, drops to ~130
        dia_bp = 95 - (i * 3) + random.randint(-2, 2)   # Starts 95, drops to ~83
        hr = 72 + random.randint(-5, 5)
        glucose = 95 + random.randint(-10, 10)
        
        # Create HL7 Message
        msg_id = i + 1000 # Offset to avoid collision
        raw_hl7 = f"MSH|^~\\&|SEND|REC|0|0|{visit_date_str}||ORU^R01|{msg_id}|P|2.3\rPID|1||{patient_id}||{last_name}^{first_name}||{dob}|{sex}"
        
        cursor.execute("""
            INSERT INTO hl7_messages (patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, received_at, raw_hl7)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (patient_id, first_name, last_name, dob, sex, visit_date.strftime("%Y-%m-%d %H:%M:%S"), raw_hl7))
        
        db_msg_id = cursor.lastrowid
        
        # Add Observations
        # BP Systolic
        cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime) VALUES (?, ?, ?, ?, ?, ?)",
                       (db_msg_id, "8480-6", "Systolic Blood Pressure", sys_bp, "mmHg", visit_date_str))
        
        # BP Diastolic
        cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime) VALUES (?, ?, ?, ?, ?, ?)",
                       (db_msg_id, "8462-4", "Diastolic Blood Pressure", dia_bp, "mmHg", visit_date_str))
                       
        # Heart Rate
        cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime) VALUES (?, ?, ?, ?, ?, ?)",
                       (db_msg_id, "8867-4", "Heart Rate", hr, "bpm", visit_date_str))

        # Glucose
        cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime) VALUES (?, ?, ?, ?, ?, ?)",
                       (db_msg_id, "2345-7", "Glucose", glucose, "mg/dL", visit_date_str))

    conn.commit()
    conn.close()
    print("SUCCESS: Seeded 5 months of vital signs history.")

if __name__ == "__main__":
    seed_vitals_history()
