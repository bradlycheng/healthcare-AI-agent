import sqlite3
import random
import uuid
import os
from datetime import datetime, timedelta
from .db import DB_PATH, init_db, delete_all_messages, get_connection

# Constants
LOINC_MAP = {
    "Heart Rate": {"code": "8867-4", "unit": "bpm", "min": 60, "max": 100},
    "Systolic BP": {"code": "8480-6", "unit": "mmHg", "min": 90, "max": 120},
    "Diastolic BP": {"code": "8462-4", "unit": "mmHg", "min": 60, "max": 80},
    "Respiratory Rate": {"code": "9279-1", "unit": "breaths/min", "min": 12, "max": 20},
    "SpO2": {"code": "2708-6", "unit": "%", "min": 95, "max": 100},
    "Body Temperature": {"code": "8310-5", "unit": "F", "min": 97.0, "max": 99.0},
    "Glucose": {"code": "2339-0", "unit": "mg/dL", "min": 70, "max": 100},
    "Total Cholesterol": {"code": "2093-3", "unit": "mg/dL", "min": 125, "max": 200},
    "HDL": {"code": "2085-9", "unit": "mg/dL", "min": 40, "max": 60},
    "LDL": {"code": "13457-7", "unit": "mg/dL", "min": 0, "max": 100},
    "Triglycerides": {"code": "2571-8", "unit": "mg/dL", "min": 0, "max": 150},
    "Hemoglobin A1c": {"code": "4548-4", "unit": "%", "min": 4.0, "max": 5.6},
    "TSH": {"code": "3016-3", "unit": "uIU/mL", "min": 0.4, "max": 4.0},
    "ALT": {"code": "1742-6", "unit": "U/L", "min": 7, "max": 55},
    "AST": {"code": "1920-8", "unit": "U/L", "min": 8, "max": 48},
    "Serum Creatinine": {"code": "2160-0", "unit": "mg/dL", "min": 0.6, "max": 1.2},
    "BUN": {"code": "3094-0", "unit": "mg/dL", "min": 7, "max": 20},
    "eGFR": {"code": "33914-3", "unit": "mL/min/1.73m2", "min": 90, "max": 120}
}

FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth", 
               "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Charles", "Karen"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

PROVIDERS = ["Dr. Alice Chen", "Dr. Bob Smith", "Dr. Carol White", "Dr. David Kim", "NP Emily Davis"]

CONDITIONS = {
    "Diabetes": {
        "dx_code": "E11.9", 
        "dx_name": "Type 2 diabetes mellitus without complications",
        "meds": [("Metformin", "500 mg", "Twice daily"), ("Glipizide", "5 mg", "Daily")],
        "labs": ["Glucose", "Hemoglobin A1c"]
    },
    "Hypertension": {
        "dx_code": "I10", 
        "dx_name": "Essential (primary) hypertension",
        "meds": [("Lisinopril", "10 mg", "Daily"), ("Amlodipine", "5 mg", "Daily")],
        "labs": ["Systolic BP", "Diastolic BP"]
    },
    "Hyperlipidemia": {
        "dx_code": "E78.5", 
        "dx_name": "Hyperlipidemia, unspecified",
        "meds": [("Atorvastatin", "20 mg", "Daily"), ("Simvastatin", "40 mg", "Nightly")],
        "labs": ["Total Cholesterol", "LDL", "HDL", "Triglycerides"]
    },
    "CKD": {
        "dx_code": "N18.3",
        "dx_name": "Chronic kidney disease, stage 3 (moderate)",
        "meds": [("Furosemide", "20 mg", "Daily")],
        "labs": ["Serum Creatinine", "BUN", "eGFR"]
    }
}

def generate_dob(age):
    year = 2026 - age
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"

def seed_database(verbose=True, use_llm=False):
    """
    Seed database with realistic sample data (100 patients).
    Parameters match API signature but use_llm is ignored as this uses direct SQL for speed.
    """
    if verbose:
        print("Initializing Database...")
    
    # 1. Init Tables
    init_db()
    
    # 2. Clear Existing Data
    print("Clearing existing data via delete_all_messages()...")
    delete_all_messages()
    print("Data cleared successfully.")

    # 3. Connect (use get_connection for timeout/WAL settings)
    db_path = os.getenv("DATABASE_PATH", DB_PATH)
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # --- EXPERT SCENARIO PATIENTS (Data Primed for Dashboard) ---
    print("Seeding Expert Scenario Patients...")
    
    # 1. Diabetic Dave (High Glucose)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-DIABETIC", "Diabetic", "Dave", "1970-01-01", "M", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status) VALUES ('P-DIABETIC', 'E11.9', 'Type 2 diabetes mellitus', '2025-01-01', 'Active')")
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '2339-0', 'Glucose', 250, 'mg/dL', ?, 'F', 'H', 'WARNING')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 2. Feverish Fiona (High Temp)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-FEVER", "Feverish", "Fiona", "1990-02-14", "F", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '8310-5', 'Body Temperature', 103.5, 'F', ?, 'F', 'H', 'WARNING')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 3. Normal Nancy (All Normal)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-NORMAL", "Normal", "Nancy", "1985-11-20", "F", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '8867-4', 'Heart Rate', 72, 'bpm', ?, 'F', 'N', NULL)", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '8480-6', 'Systolic BP', 115, 'mmHg', ?, 'F', 'N', NULL)", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    # 4. Hypertensive Harry (High BP)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-HTN", "Hypertensive", "Harry", "1960-04-10", "M", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status) VALUES ('P-HTN', 'I10', 'Essential (primary) hypertension', '2020-01-01', 'Active')")
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '8480-6', 'Systolic BP', 185, 'mmHg', ?, 'F', 'H', 'CRITICAL')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    
    # 5. Tachycardic Tom (High HR Warning)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-TACHY", "Tachycardic", "Tom", "1975-09-30", "M", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '8867-4', 'Heart Rate', 115, 'bpm', ?, 'F', 'H', 'WARNING')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 6. Hypoglycemic Hannah (Low Glucose)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-HYPO", "Hypoglycemic", "Hannah", "1988-06-15", "F", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '2339-0', 'Glucose', 55, 'mg/dL', ?, 'F', 'L', 'CRITICAL')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    # 4. CKD Charlie (Low eGFR)
    cursor.execute("INSERT INTO hl7_messages (received_at, raw_hl7, patient_id, patient_first_name, patient_last_name, patient_dob, patient_sex, fhir_bundle_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Expert Data", "P-CKD", "CKD", "Charlie", "1955-08-20", "M", "{}"))
    msg_id = cursor.lastrowid
    cursor.execute("INSERT INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status) VALUES ('P-CKD', 'N18.3', 'Chronic kidney disease, stage 3', '2024-06-01', 'Active')")
    cursor.execute("INSERT INTO observations (message_id, code, display, value_num, unit, observation_datetime, status, flag, alert_level) VALUES (?, '33914-3', 'eGFR', 45, 'mL/min/1.73m2', ?, 'F', 'L', 'WARNING')", (msg_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()

    
    # Generate 100 Patients (Deterministic)
    if verbose:
        print("Generating 100 Sample Patients (Deterministic)...")
        
    random.seed(42)  # Ensure consistency
    
    # --- FIXED DEMO PATIENTS ---
    DEMO_PATIENTS = [
        {"id": "P-SARAH", "first": "Sarah", "last": "Jenkins", "sex": "F", "age": 45, "conditions": ["Hypertension"]},
        {"id": "P-JOHN", "first": "John", "last": "Smith", "sex": "M", "age": 62, "conditions": ["Diabetes", "CKD"]}
    ]
    
    for i in range(30):
        if i < len(DEMO_PATIENTS):
            dp = DEMO_PATIENTS[i]
            pid, first, last, sex, age, patient_conditions = dp["id"], dp["first"], dp["last"], dp["sex"], dp["age"], dp["conditions"]
        else:
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            if i % 5 == 0: 
                # Ensure some duplicates or specific patterns for search testing
                last = "SearchTest" 
                
            sex = random.choice(["M", "F"])
            age = random.randint(25, 85)
            pid = f"P{10000+i}"
            
            # Assign Conditions
            patient_conditions = []
            if random.random() < 0.3: # 30% chance of HTN
                patient_conditions.append("Hypertension")
            if random.random() < 0.15: # 15% chance of Diabetes
                patient_conditions.append("Diabetes")
            if random.random() < 0.25: # 25% chance of High Cholesterol
                patient_conditions.append("Hyperlipidemia")
            
        dob = generate_dob(age)
            
        # Generate Visits & Data (Over 2 years)
        num_visits = random.randint(3, 12)
        base_date = datetime.now() - timedelta(days=730)
        
        for v in range(num_visits):
            visit_date = base_date + timedelta(days=random.randint(0, 700))
            visit_id = f"V{uuid.uuid4().hex[:8]}"
            date_str = visit_date.strftime("%Y-%m-%d %H:%M:%S")
            provider = random.choice(PROVIDERS)
            
            # Create Visit
            cursor.execute("""
                INSERT INTO visits (visit_id, patient_id, visit_date, visit_type, provider_name, chief_complaint)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (visit_id, pid, date_str, "Outpatient", provider, "Routine Follow-up"))
            
            # Determine obs to run
            vitals = ["Heart Rate", "Systolic BP", "Diastolic BP", "Body Temperature"]
            labs_to_run = list(vitals)
            for cond in patient_conditions:
                labs_to_run.extend(CONDITIONS[cond]["labs"])
            if random.random() < 0.2:
                labs_to_run.extend(["TSH", "ALT", "AST"])
            labs_to_run = list(set(labs_to_run))
            
            # --- Inline Message Insertion ---
            raw_hl7_mock = f"Generated Historical Data for {pid}"
            
            cursor.execute(
                """
                INSERT INTO hl7_messages (
                  received_at, raw_hl7, patient_id, patient_first_name, 
                  patient_last_name, patient_dob, patient_sex, fhir_bundle_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (date_str, raw_hl7_mock, pid, first, last, dob, sex, "{}")
            )
            message_id = cursor.lastrowid
            
            # --- Inline Observations ---
            for lab_name in labs_to_run:
                loinc_info = LOINC_MAP[lab_name]
                
                # Logic for abnormal values
                # Use uniform for everything to handle floats (e.g. A1c 4.0-5.6)
                val = random.uniform(loinc_info["min"], loinc_info["max"])
                
                if "Diabetes" in patient_conditions and lab_name == "Glucose":
                    val = random.uniform(110, 250)
                if "Hypertension" in patient_conditions and "BP" in lab_name:
                    val *= random.uniform(1.1, 1.4)
                if "Hyperlipidemia" in patient_conditions and lab_name == "LDL":
                    val = random.uniform(110, 190)
                
                # Round appropriately
                if "BP" in lab_name or "Rate" in lab_name:
                    val = int(round(val))
                else:
                    val = round(val, 1)
                
                flag = "N"
                if val < loinc_info["min"]: flag = "L"
                if val > loinc_info["max"]: flag = "H"
                
                cursor.execute(
                    """
                    INSERT INTO observations (
                      message_id, code, display, value_num, value_raw, unit,
                      reference_low, reference_high, flag, observation_datetime,
                      status, loinc_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message_id, 
                        loinc_info["code"], 
                        lab_name, 
                        val, 
                        str(val), 
                        loinc_info["unit"],
                        str(loinc_info["min"]), 
                        str(loinc_info["max"]), 
                        flag, 
                        date_str, 
                        "F",
                        loinc_info["code"]
                    )
                )

        # Add Conditions (Diagnoses)
        for cond_name in patient_conditions:
            cond_data = CONDITIONS[cond_name]
            dx_date = (base_date - timedelta(days=random.randint(100, 300))).strftime("%Y-%m-%d")
            cursor.execute("""
                INSERT INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status)
                VALUES (?, ?, ?, ?, ?)
            """, (pid, cond_data["dx_code"], cond_data["dx_name"], dx_date, "Active"))
            
            # Add Meds
            for med in cond_data["meds"]:
                cursor.execute("""
                    INSERT INTO medications (patient_id, medication_name, dosage, frequency, start_date, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (pid, med[0], med[1], med[2], dx_date, "Active"))

    conn.commit()
    conn.close()
    if verbose:
        print("Seed Complete: 100 Patients, Visits, Observations, Meds, and Diagnoses created.")

if __name__ == "__main__":
    seed_database()
