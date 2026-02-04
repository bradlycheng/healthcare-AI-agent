
import sqlite3
from app.db import DB_PATH

def verify():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    tables = ["hl7_messages", "observations", "visits", "medications", "diagnoses"]
    for t in tables:
        try:
            count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"Table '{t}': {count} rows")
        except Exception as e:
            print(f"Table '{t}': Error - {e}")

    # Check for a diabetic patient
    print("\n--- Diabetic Patient Sample ---")
    
    # Corrected SQL Query to handle potential casing issues
    diabetics = cur.execute("""
        SELECT DISTINCT patient_id FROM diagnoses 
        WHERE diagnosis_name LIKE '%Diabetes%'
        LIMIT 1
    """).fetchone()

    if diabetics:
        pid = diabetics[0]
        print(f"Found Diabetic Patient: {pid}")
        
        meds = cur.execute("SELECT medication_name FROM medications WHERE patient_id = ?", (pid,)).fetchall()
        print(f"Meds: {[m[0] for m in meds]}")
        
        # Check glucose levels (using loinc_code if possible, else display)
        glucose = cur.execute("""
            SELECT AVG(value_num) FROM observations 
            WHERE display = 'Glucose' AND message_id IN (
                SELECT id FROM hl7_messages WHERE patient_id = ?
            )
        """, (pid,)).fetchone()
        print(f"Avg Glucose: {glucose[0]}")
    else:
        print("No diabetic patients found.")

    conn.close()

if __name__ == "__main__":
    verify()
