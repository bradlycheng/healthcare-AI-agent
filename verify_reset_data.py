
import sqlite3
import os
import sys

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from app.seed import seed_database
from app.db import get_connection, DB_PATH

def verify_data():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()
    
    print("Verifying Expert Data...")
    
    # 1. Check Diabetic Dave
    cursor.execute("SELECT patient_first_name, value_num FROM hl7_messages h JOIN observations o ON h.id = o.message_id WHERE h.patient_id = 'P-DIABETIC' AND o.display = 'Glucose'")
    dave = cursor.fetchone()
    if dave and dave[0] == 'Diabetic' and dave[1] == 250:
        print("[OK] Diabetic Dave found with Glucose 250")
    else:
        print(f"[FAIL] Diabetic Dave mismatch: {dave}")

    # 2. Check Feverish Fiona
    cursor.execute("SELECT patient_first_name, value_num FROM hl7_messages h JOIN observations o ON h.id = o.message_id WHERE h.patient_id = 'P-FEVER' AND o.display = 'Body Temperature'")
    fiona = cursor.fetchone()
    if fiona and fiona[0] == 'Feverish' and fiona[1] == 103.5:
        print("[OK] Feverish Fiona found with Temp 103.5")
    else:
        print(f"[FAIL] Feverish Fiona mismatch: {fiona}")

    # 3. Check CKD Charlie
    cursor.execute("SELECT patient_first_name, value_num FROM hl7_messages h JOIN observations o ON h.id = o.message_id WHERE h.patient_id = 'P-CKD' AND o.display = 'eGFR'")
    charlie = cursor.fetchone()
    if charlie and charlie[0] == 'CKD' and charlie[1] == 45:
        print("[OK] CKD Charlie found with eGFR 45")
    else:
        print(f"[FAIL] CKD Charlie mismatch: {charlie}")
        
    conn.close()

if __name__ == "__main__":
    # Simulate Reset
    print("--- Simulating Reset ---")
    seed_database(verbose=False)
    verify_data()
