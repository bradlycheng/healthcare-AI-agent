# app/seed.py
"""
Realistic Sample Data for Healthcare AI Agent
20 patients with longitudinal data, comorbidities, and realistic medical patterns
"""
from typing import List
from datetime import datetime, timedelta
import random
from .agent import run_oru_pipeline
from .db import init_db

def generate_realistic_messages() -> List[str]:
    """Generate realistic HL7 messages for 20 patients with longitudinal data"""
    
    messages = []
    
    # Utility function to generate dates
    def days_ago(days):
        return (datetime.now() - timedelta(days=days)).strftime("%Y%m%d%H%M")
    
    # =========================================================================
    # PATIENT 1: Sarah Johnson - Type 2 Diabetes (well-controlled)
    # =========================================================================
    # Initial visit - 90 days ago
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(90)}||ORU^R01|MSG001A|P|2.5
PID|1||10001||JOHNSON^SARAH||19880615|F
OBR|1|ORD001A|RES001A|DIAB^Diabetes Panel|||{days_ago(90)}
OBX|1|NM|2345-7^GLUCOSE||156|mg/dL|70-100|H|||F
OBX|2|NM|4548-4^HBA1C||7.8|%|4.0-5.6|H|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||128|mmHg|90-120|H|||F
OBX|4|NM|8462-4^DIASTOLIC_BP||82|mmHg|60-80|H|||F
OBX|5|TX|NOTE^Clinical Note||New diagnosis Type 2 Diabetes. Start metformin 500mg BID.||||||F""")
    
    # Follow-up - 30 days ago (improving)
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(30)}||ORU^R01|MSG001B|P|2.5
PID|1||10001||JOHNSON^SARAH||19880615|F
OBR|1|ORD001B|RES001B|GLUC^Glucose Check|||{days_ago(30)}
OBX|1|NM|2345-7^GLUCOSE||118|mg/dL|70-100|H|||F
OBX|2|NM|4548-4^HBA1C||6.4|%|4.0-5.6|H|||F
OBX|3|TX|NOTE^Clinical Note||Diabetes improving on metformin. Continue current regimen.||||||F""")
    
    # Recent - 7 days ago (well-controlled)
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(7)}||ORU^R01|MSG001C|P|2.5
PID|1||10001||JOHNSON^SARAH||19880615|F
OBR|1|ORD001C|RES001C|GLUC^Glucose Check|||{days_ago(7)}
OBX|1|NM|2345-7^GLUCOSE||98|mg/dL|70-100|N|||F
OBX|2|TX|NOTE^Clinical Note||Excellent glucose control achieved.||||||F""")
    
    # =========================================================================
    # PATIENT 2: Michael Chen - Hypertension + High Cholesterol
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(120)}||ORU^R01|MSG002A|P|2.5
PID|1||10002||CHEN^MICHAEL||19750420|M
OBR|1|ORD002A|RES002A|CARD^Cardiac Panel|||{days_ago(120)}
OBX|1|NM|8480-6^SYSTOLIC_BP||158|mmHg|90-120|H|||F
OBX|2|NM|8462-4^DIASTOLIC_BP||98|mmHg|60-80|H|||F
OBX|3|NM|2093-3^CHOLESTEROL||285|mg/dL|0-200|H|||F
OBX|4|NM|13457-7^LDL||195|mg/dL|0-100|H|||F
OBX|5|NM|2085-9^HDL||38|mg/dL|40-60|L|||F
OBX|6|TX|NOTE^Clinical Note||Hypertension Stage 2 + hyperlipidemia. Start lisinopril and atorvastatin.||||||F""")
    
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(15)}||ORU^R01|MSG002B|P|2.5
PID|1||10002||CHEN^MICHAEL||19750420|M
OBR|1|ORD002B|RES002B|LIPID^Lipid Panel|||{days_ago(15)}
OBX|1|NM|8480-6^SYSTOLIC_BP||132|mmHg|90-120|H|||F
OBX|2|NM|8462-4^DIASTOLIC_BP||84|mmHg|60-80|H|||F
OBX|3|NM|2093-3^CHOLESTEROL||215|mg/dL|0-200|H|||F
OBX|4|NM|13457-7^LDL||135|mg/dL|0-100|H|||F
OBX|5|TX|NOTE^Clinical Note||BP and cholesterol improving on medications.||||||F""")
    
    # =========================================================================
    # PATIENT 3: Emily Rodriguez - Thyroid Disorder
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(60)}||ORU^R01|MSG003|P|2.5
PID|1||10003||RODRIGUEZ^EMILY||19920308|F
OBR|1|ORD003|RES003|THYR^Thyroid Panel|||{days_ago(60)}
OBX|1|NM|3016-3^TSH||8.5|mIU/L|0.4-4.0|H|||F
OBX|2|NM|3026-2^FREE_T4||0.6|ng/dL|0.8-1.8|L|||F
OBX|3|NM|8867-4^HEART_RATE||58|bpm|60-100|L|||F
OBX|4|TX|NOTE^Clinical Note||Hypothyroidism. Start levothyroxine 50mcg daily.||||||F""")
    
    # =========================================================================
    # PATIENT 4: James Patterson - Acute MI (Cardiac Event)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(3)}||ORU^R01|MSG004|P|2.5
PID|1||10004||PATTERSON^JAMES||19680912|M
OBR|1|ORD004|RES004|CARD^Cardiac Markers|||{days_ago(3)}
OBX|1|NM|10839-9^TROPONIN_I||2.8|ng/mL|0.0-0.04|H|||F
OBX|2|NM|13969-1^CK_MB||45|ng/mL|0-5|H|||F
OBX|3|NM|2345-7^GLUCOSE||145|mg/dL|70-100|H|||F
OBX|4|TX|NOTE^Clinical Note||ACUTE MI - Elevated troponin. Admitted to ICU. Cardiac cath scheduled.||||||F""")
    
    # =========================================================================
    # PATIENT 5: Linda Martinez - Healthy Annual Checkup
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(14)}||ORU^R01|MSG005|P|2.5
PID|1||10005||MARTINEZ^LINDA||19950722|F
OBR|1|ORD005|RES005|WELL^Wellness Panel|||{days_ago(14)}
OBX|1|NM|2345-7^GLUCOSE||88|mg/dL|70-100|N|||F
OBX|2|NM|718-7^HEMOGLOBIN||13.8|g/dL|12.0-16.0|N|||F
OBX|3|NM|6690-2^WBC||7200|/uL|4500-11000|N|||F
OBX|4|NM|8480-6^SYSTOLIC_BP||118|mmHg|90-120|N|||F
OBX|5|NM|8867-4^HEART_RATE||68|bpm|60-100|N|||F
OBX|6|TX|NOTE^Clinical Note||Healthy 29yo female. All values within normal limits.||||||F""")
    
    # =========================================================================
    # PATIENT 6: Robert Thompson - CKD (Chronic Kidney Disease)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(45)}||ORU^R01|MSG006|P|2.5
PID|1||10006||THOMPSON^ROBERT||19601205|M
OBR|1|ORD006|RES006|RENAL^Renal Panel|||{days_ago(45)}
OBX|1|NM|2160-0^CREATININE||2.8|mg/dL|0.6-1.2|H|||F
OBX|2|NM|3094-0^BUN||42|mg/dL|7-20|H|||F
OBX|3|NM|2823-3^POTASSIUM||5.8|mmol/L|3.5-5.0|H|||F
OBX|4|TX|NOTE^Clinical Note||CKD Stage 3. Monitor potassium. Nephrology referral.||||||F""")
    
    # =========================================================================
    # PATIENT 7: Jennifer Lee - Anemia (Iron Deficiency)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(25)}||ORU^R01|MSG007|P|2.5
PID|1||10007||LEE^JENNIFER||19850518|F
OBR|1|ORD007|RES007|CBC^Complete Blood Count|||{days_ago(25)}
OBX|1|NM|718-7^HEMOGLOBIN||9.5|g/dL|12.0-16.0|L|||F
OBX|2|NM|789-8^RBC||3.9|10*6/uL|4.0-5.5|L|||F
OBX|3|NM|787-2^MCV||72|fL|80-100|L|||F
OBX|4|NM|2498-4^IRON||35|mcg/dL|50-170|L|||F
OBX|5|TX|NOTE^Clinical Note||Microcytic anemia. Likely iron deficiency. Start iron supplementation.||||||F""")
    
    # =========================================================================
    # PATIENT 8: David Wilson - Pre-diabetes
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(50)}||ORU^R01|MSG008|P|2.5
PID|1||10008||WILSON^DAVID||19780923|M
OBR|1|ORD008|RES008|DIAB^Diabetes Screening|||{days_ago(50)}
OBX|1|NM|2345-7^GLUCOSE||118|mg/dL|70-100|H|||F
OBX|2|NM|4548-4^HBA1C||6.2|%|4.0-5.6|H|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||134|mmHg|90-120|H|||F
OBX|4|TX|NOTE^Clinical Note||Pre-diabetes. Lifestyle modifications recommended. Recheck in 3 months.||||||F""")
    
    # =========================================================================
    # PATIENT 9: Maria Garcia - Healthy Pregnancy Monitoring
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(10)}||ORU^R01|MSG009|P|2.5
PID|1||10009||GARCIA^MARIA||19930127|F
OBR|1|ORD009|RES009|OB^OB Panel|||{days_ago(10)}
OBX|1|NM|2345-7^GLUCOSE||92|mg/dL|70-100|N|||F
OBX|2|NM|718-7^HEMOGLOBIN||11.8|g/dL|12.0-16.0|L|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||112|mmHg|90-120|N|||F
OBX|4|TX|NOTE^Clinical Note||26 weeks pregnant. Mild physiologic anemia. Otherwise normal.||||||F""")
    
    # =========================================================================
    # PATIENT 10: Christopher Brown - Infection (Elevated WBC)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(5)}||ORU^R01|MSG010|P|2.5
PID|1||10010||BROWN^CHRISTOPHER||19990814|M
OBR|1|ORD010|RES010|CBC^Complete Blood Count|||{days_ago(5)}
OBX|1|NM|6690-2^WBC||18500|/uL|4500-11000|H|||F
OBX|2|NM|8310-5^BODY_TEMP||101.2|degF|97.0-99.0|H|||F
OBX|3|NM|718-7^HEMOGLOBIN||14.5|g/dL|13.5-17.5|N|||F
OBX|4|TX|NOTE^Clinical Note||Acute bacterial infection. Start antibiotics. Follow-up in 48 hours.||||||F""")
    
    # =========================================================================
    # PATIENT 11: Amanda Davis - Liver Enzymes Elevated
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(35)}||ORU^R01|MSG011|P|2.5
PID|1||10011||DAVIS^AMANDA||19870403|F
OBR|1|ORD011|RES011|LIVER^Liver Panel|||{days_ago(35)}
OBX|1|NM|1742-6^ALT||85|U/L|7-55|H|||F
OBX|2|NM|1920-8^AST||95|U/L|8-48|H|||F
OBX|3|NM|1975-2^BILIRUBIN||1.8|mg/dL|0.1-1.2|H|||F
OBX|4|TX|NOTE^Clinical Note||Elevated liver enzymes. Likely medication-induced. Discontinue statin temporarily.||||||F""")
    
    # =========================================================================
    # PATIENT 12: Kevin Anderson - Controlled Hypertension
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(20)}||ORU^R01|MSG012|P|2.5
PID|1||10012||ANDERSON^KEVIN||19651118|M
OBR|1|ORD012|RES012|BP^Blood Pressure Check|||{days_ago(20)}
OBX|1|NM|8480-6^SYSTOLIC_BP||122|mmHg|90-120|H|||F
OBX|2|NM|8462-4^DIASTOLIC_BP||78|mmHg|60-80|N|||F
OBX|3|NM|8867-4^HEART_RATE||74|bpm|60-100|N|||F
OBX|4|TX|NOTE^Clinical Note||BP well-controlled on lisinopril 10mg. Continue current dose.||||||F""")
    
    # =========================================================================
    # PATIENT 13: Nicole Taylor - Healthy Young Adult
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(40)}||ORU^R01|MSG013|P|2.5
PID|1||10013||TAYLOR^NICOLE||20000512|F
OBR|1|ORD013|RES013|WELL^Wellness Check|||{days_ago(40)}
OBX|1|NM|2345-7^GLUCOSE||85|mg/dL|70-100|N|||F
OBX|2|NM|718-7^HEMOGLOBIN||13.2|g/dL|12.0-16.0|N|||F
OBX|3|NM|2093-3^CHOLESTEROL||165|mg/dL|0-200|N|||F
OBX|4|NM|8480-6^SYSTOLIC_BP||115|mmHg|90-120|N|||F
OBX|5|TX|NOTE^Clinical Note||Healthy 24yo. All normal. Continue healthy lifestyle.||||||F""")
    
    # =========================================================================
    # PATIENT 14: Brian Moore - COPD (Respiratory)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(18)}||ORU^R01|MSG014|P|2.5
PID|1||10014||MOORE^BRIAN||19581230|M
OBR|1|ORD014|RES014|RESP^Respiratory Panel|||{days_ago(18)}
OBX|1|NM|2710-2^O2_SAT||88|%|95-100|L|||F
OBX|2|NM|8867-4^HEART_RATE||92|bpm|60-100|N|||F
OBX|3|NM|6690-2^WBC||9200|/uL|4500-11000|N|||F
OBX|4|TX|NOTE^Clinical Note||COPD exacerbation. Low oxygen saturation. Start oxygen therapy 2L/min.||||||F""")
    
    # =========================================================================
    # PATIENT 15: Rachel White - Vitamin D Deficiency
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(28)}||ORU^R01|MSG015|P|2.5
PID|1||10015||WHITE^RACHEL||19911009|F
OBR|1|ORD015|RES015|VIT^Vitamin Panel|||{days_ago(28)}
OBX|1|NM|1989-3^VITAMIN_D||18|ng/mL|30-100|L|||F
OBX|2|NM|17861-6^CALCIUM||9.2|mg/dL|8.5-10.5|N|||F
OBX|3|TX|NOTE^Clinical Note||Vitamin D deficiency. Start cholecalciferol 2000 IU daily.||||||F""")
    
    # =========================================================================
    # PATIENT 16: Daniel Harris - Gout (Elevated Uric Acid)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(12)}||ORU^R01|MSG016|P|2.5
PID|1||10016||HARRIS^DANIEL||19720625|M
OBR|1|ORD016|RES016|GOUT^Gout Panel|||{days_ago(12)}
OBX|1|NM|3084-1^URIC_ACID||9.8|mg/dL|3.5-7.2|H|||F
OBX|2|NM|6690-2^WBC||11200|/uL|4500-11000|H|||F
OBX|3|TX|NOTE^Clinical Note||Acute gout attack. Elevated uric acid. Start allopurinol after acute phase.||||||F""")
    
    # =========================================================================
    # PATIENT 17: Jessica Clark - Electrolyte Imbalance
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(8)}||ORU^R01|MSG017|P|2.5
PID|1||10017||CLARK^JESSICA||19960219|F
OBR|1|ORD017|RES017|BMP^Basic Metabolic Panel|||{days_ago(8)}
OBX|1|NM|2951-2^SODIUM||128|mmol/L|136-145|L|||F
OBX|2|NM|2823-3^POTASSIUM||3.2|mmol/L|3.5-5.0|L|||F
OBX|3|NM|2075-0^CHLORIDE||96|mmol/L|98-107|L|||F
OBX|4|TX|NOTE^Clinical Note||Hyponatremia + hypokalemia. Likely dehydration. IV fluids initiated.||||||F""")
    
    # =========================================================================
    # PATIENT 18: Mark Lewis - Polycythemia (High RBC)
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(22)}||ORU^R01|MSG018|P|2.5
PID|1||10018||LEWIS^MARK||19550807|M
OBR|1|ORD018|RES018|CBC^Complete Blood Count|||{days_ago(22)}
OBX|1|NM|718-7^HEMOGLOBIN||19.2|g/dL|13.5-17.5|H|||F
OBX|2|NM|789-8^RBC||6.8|10*6/uL|4.5-5.9|H|||F
OBX|3|NM|4544-3^HEMATOCRIT||58|%|39-49|H|||F
OBX|4|TX|NOTE^Clinical Note||Polycythemia vera suspected. Hematology referral for workup.||||||F""")
    
    # =========================================================================
    # PATIENT 19: Sophia Robinson - Metabolic Syndrome
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(16)}||ORU^R01|MSG019|P|2.5
PID|1||10019||ROBINSON^SOPHIA||19690314|F
OBR|1|ORD019|RES019|METAB^Metabolic Panel|||{days_ago(16)}
OBX|1|NM|2345-7^GLUCOSE||128|mg/dL|70-100|H|||F
OBX|2|NM|4548-4^HBA1C||6.8|%|4.0-5.6|H|||F
OBX|3|NM|2093-3^CHOLESTEROL||268|mg/dL|0-200|H|||F
OBX|4|NM|8480-6^SYSTOLIC_BP||142|mmHg|90-120|H|||F
OBX|5|NM|2571-8^TRIGLYCERIDES||225|mg/dL|0-150|H|||F
OBX|6|TX|NOTE^Clinical Note||Metabolic syndrome - diabetes, hypertension, dyslipidemia. Aggressive lifestyle intervention.||||||F""")
    
    # =========================================================================
    # PATIENT 20: Anthony Scott - Healthy Senior
    # =========================================================================
    messages.append(f"""MSH|^~\\&|HIS|MedCenter|LIS|LAB|{days_ago(30)}||ORU^R01|MSG020|P|2.5
PID|1||10020||SCOTT^ANTHONY||19520603|M
OBR|1|ORD020|RES020|SENIOR^Senior Wellness|||{days_ago(30)}
OBX|1|NM|2345-7^GLUCOSE||94|mg/dL|70-100|N|||F
OBX|2|NM|2160-0^CREATININE||1.1|mg/dL|0.6-1.2|N|||F
OBX|3|NM|2093-3^CHOLESTEROL||185|mg/dL|0-200|N|||F
OBX|4|NM|8480-6^SYSTOLIC_BP||125|mmHg|90-120|H|||F
OBX|5|NM|8867-4^HEART_RATE||68|bpm|60-100|N|||F
OBX|6|TX|NOTE^Clinical Note||Healthy 72yo male. Mild hypertension controlled. Overall excellent health.||||||F""")
    
    return messages

def seed_database(verbose=True):
    """Seed database with realistic sample data"""
    import sqlite3
    import os
    
    DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
    
    if verbose:
        print("Initializing database...")
    init_db()
    
    if verbose:
        print("Generating realistic sample data for 20 patients...")
    
    messages = generate_realistic_messages()
    
    if verbose:
        print(f"Processing {len(messages)} HL7 messages...")
    
    for i, msg in enumerate(messages, 1):
        if verbose:
            print(f"  [{i}/{len(messages)}] Processing message...")
        run_oru_pipeline(msg)
    
    # Add medications, diagnoses, and visits for key patients
    if verbose:
        print("Adding medications, diagnoses, and visits...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Sample medications (matching clinical notes in HL7 messages)
    medications = [
        ("10001", "Metformin", "500 mg", "BID", "2025-10-01", None, "Active"),  # Sarah Johnson - Diabetes
        ("10002", "Lisinopril", "10 mg", "Daily", "2025-09-01", None, "Active"),  # Michael Chen - HTN
        ("10002", "Atorvastatin", "20 mg", "Daily", "2025-09-01", None, "Active"),  # Michael Chen - Cholesterol
        ("10003", "Levothyroxine", "50 mcg", "Daily", "2025-11-01", None, "Active"),  # Emily Rodriguez - Thyroid
        ("10012", "Lisinopril", "10 mg", "Daily", "2025-01-01", None, "Active"),  # Kevin Anderson - HTN
        ("10015", "Vitamin D", "2000 IU", "Daily", "2025-12-01", None, "Active"),  # Rachel White - Vit D
    ]
    
    for med in medications:
        cursor.execute("""
            INSERT INTO medications (patient_id, medication_name, dosage, frequency, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, med)
    
    # Sample diagnoses
    diagnoses = [
        ("10001", "E11.9", "Type 2 Diabetes Mellitus", "2025-10-01", "Active"),
        ("10002", "I10", "Essential Hypertension", "2025-09-01", "Active"),
        ("10002", "E78.0", "Hyperlipidemia", "2025-09-01", "Active"),
        ("10003", "E03.9", "Hypothyroidism", "2025-11-01", "Active"),
        ("10004", "I21.9", "Acute Myocardial Infarction", "2025-01-28", "Active"),
        ("10006", "N18.3", "Chronic Kidney Disease Stage 3", "2024-12-01", "Active"),
        ("10008", "R73.03", "Prediabetes", "2025-11-01", "Active"),
        ("10014", "J44.1", "COPD with Exacerbation", "2025-01-15", "Active"),
        ("10019", "E66.9", "Metabolic Syndrome", "2025-01-17", "Active"),
    ]
    
    for diag in diagnoses:
        cursor.execute("""
            INSERT INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status)
            VALUES (?, ?, ?, ?, ?)
        """, diag)
    
    # Sample visits
    visits = [
        ("V001", "10001", "2025-10-01", "Outpatient", "Dr. Smith", "New diabetes diagnosis"),
        ("V002", "10001", "2025-12-01", "Outpatient", "Dr. Smith", "Diabetes follow-up"),
        ("V003", "10002", "2025-09-01", "Outpatient", "Dr. Jones", "Hypertension workup"),
        ("V004", "10004", "2025-01-28", "Emergency", "Dr. Williams", "Chest pain"),
        ("V005", "10006", "2024-12-15", "Outpatient", "Dr. Chen", "Kidney function check"),
    ]
    
    for visit in visits:
        cursor.execute("""
            INSERT INTO visits (visit_id, patient_id, visit_date, visit_type, provider_name, chief_complaint)
            VALUES (?, ?, ?, ?, ?, ?)
        """, visit)
    
    conn.commit()
    conn.close()
    
    if verbose:
        print(f"\n[OK] Database seeded with {len(messages)} messages from 20 realistic patients")
        print("  - 3 diabetics (various control levels)")
        print("  - 2 cardiac patients")
        print("  - 2 hypertension")
        print("  - 2 kidney/liver issues")
        print("  - 2 blood disorders")
        print("  - 1 thyroid")
        print("  - 1 respiratory")
        print("  - 1 metabolic syndrome")
        print("  - 6 healthy/minor conditions")
        print("  Total observations: ~120")
        print(f"  Medications: {len(medications)}")
        print(f"  Diagnoses: {len(diagnoses)}")
        print(f"  Visits: {len(visits)}")

if __name__ == "__main__":
    seed_database(verbose=True)

