
import sqlite3
import datetime
import uuid

DB_PATH = "C:/Users/bradl/Desktop/healthcare_ai_agent/data/healthcare.db"

def seed_john_smith():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if John exists
    cursor.execute("SELECT id FROM hl7_messages WHERE patient_first_name = 'John' AND patient_last_name = 'Smith'")
    existing = cursor.fetchone()
    
    if existing:
        print("John Smith already exists. Ensuring data quality...")
        msg_id = existing[0]
    else:
        print("Creating John Smith...")
        msg_id = str(uuid.uuid4())
        dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO hl7_messages (id, message_type, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, message_datetime, raw_message)
            VALUES (?, 'ORU^R01', 'Pjs123', 'John', 'Smith', '1964-05-15', 'M', ?, 'SEED')
        """, (msg_id, dt))
        
    # Insert High Glucose and High A1c
    print("Inserting High Glucose and A1c for John...")
    obs_id1 = str(uuid.uuid4())
    obs_id2 = str(uuid.uuid4())
    dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Delete old obs for clear signal
    cursor.execute("DELETE FROM observations WHERE message_id = ?", (msg_id,))

    cursor.execute("""
        INSERT INTO observations (id, message_id, code, display, value_num, unit, flag, observation_datetime, status)
        VALUES 
        (?, ?, '15074-8', 'Glucose [Mass/volume] in Blood', 250, 'mg/dL', 'H', ?, 'F'),
        (?, ?, '4548-4', 'Hemoglobin A1c/Hemoglobin.total', 9.5, '%', 'H', ?, 'F')
    """, (obs_id1, msg_id, dt, obs_id2, msg_id, dt))

    conn.commit()
    conn.close()
    print("Seeding Complete: John Smith (Diabetes Profile)")

if __name__ == "__main__":
    seed_john_smith()
