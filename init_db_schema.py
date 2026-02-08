
import sqlite3
import os

DB_PATH = "C:/Users/bradl/Desktop/healthcare_ai_agent/data/healthcare.db"

def init_db():
    print(f"Initializing database at {DB_PATH}...")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS hl7_messages (
            id TEXT PRIMARY KEY,
            message_type TEXT,
            received_at TEXT,
            patient_id TEXT,
            patient_first_name TEXT,
            patient_last_name TEXT,
            patient_dob TEXT,
            patient_sex TEXT,
            message_datetime TEXT,
            raw_message TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS observations (
            id TEXT PRIMARY KEY,
            message_id TEXT,
            code TEXT,
            display TEXT,
            value_num REAL,
            value_string TEXT,
            unit TEXT,
            flag TEXT,
            observation_datetime TEXT,
            status TEXT,
            FOREIGN KEY(message_id) REFERENCES hl7_messages(id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database schema initialized.")

if __name__ == "__main__":
    init_db()
