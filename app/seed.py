# app/seed.py
from typing import List
from .agent import run_oru_pipeline
from .db import init_db

# Sample HL7 messages with various clinical scenarios
SAMPLE_MESSAGES: List[str] = [
    # Patient 1: John Smith - Diabetes + Hypertension
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412271200||ORU^R01|MSG001|P|2.5
PID|1||99001||SMITH^JOHN||19800515|M
OBR|1|ORD001|RES001|CBC^Complete Blood Count|||202412271200
OBX|1|NM|2345-7^GLUCOSE||126|mg/dL|70-100|H|||F
OBX|2|NM|718-7^HEMOGLOBIN||14.2|g/dL|13.5-17.5|N|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||138|mmHg|90-120|H|||F
OBX|4|NM|8462-4^DIASTOLIC_BP||88|mmHg|60-80|H|||F
OBX|5|TX|NOTE^Clinical Note||Glucose consistent with Type 2 Diabetes. BP indicates pre-hypertension. Monitor diet.||||||F""",

    # Patient 2: Jane Doe - Anemia
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412261430||ORU^R01|MSG002|P|2.5
PID|1||88002||DOE^JANE||19750322|F
OBR|1|ORD002|RES002|CBC^Complete Blood Count|||202412261430
OBX|1|NM|718-7^HEMOGLOBIN||9.2|g/dL|12.0-16.0|L|||F
OBX|2|NM|6690-2^WBC||12500|/uL|4500-11000|H|||F
OBX|3|NM|789-8^RBC||3.8|10*6/uL|4.0-5.5|L|||F
OBX|4|TX|NOTE^Clinical Note||Microcytic anemia likely due to iron deficiency.||||||F""",

    # Patient 3: Mary Wilson - Healthy
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412251015||ORU^R01|MSG003|P|2.5
PID|1||77003||WILSON^MARY||19901108|F
OBR|1|ORD003|RES003|CBC^Complete Blood Count|||202412251015
OBX|1|NM|718-7^HEMOGLOBIN||13.8|g/dL|12.0-16.0|N|||F
OBX|2|NM|6690-2^WBC||6800|/uL|4500-11000|N|||F
OBX|3|NM|8867-4^HEART_RATE||72|bpm|60-100|N|||F
OBX|4|TX|NOTE^Clinical Note||Healthy checkup.||||||F""",

    # Patient 4: Robert Chen - High Cholesterol
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412240900||ORU^R01|MSG004|P|2.5
PID|1||66004||CHEN^ROBERT||19650714|M
OBR|1|ORD004|RES004|LIPID^Lipid Panel|||202412240900
OBX|1|NM|2093-3^CHOLESTEROL||245|mg/dL|0-200|H|||F
OBX|2|NM|2571-8^TRIGLYCERIDES||180|mg/dL|0-150|H|||F
OBX|3|NM|13457-7^LDL||165|mg/dL|0-100|H|||F
OBX|4|TX|NOTE^Clinical Note||Hyperlipidemia. Start statin therapy.||||||F""",

    # Patient 5: Sarah Johnson - Renal Issues
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412230830||ORU^R01|MSG005|P|2.5
PID|1||55005||JOHNSON^SARAH||19880229|F
OBR|1|ORD005|RES005|BMP^Basic Metabolic Panel|||202412230830
OBX|1|NM|2160-0^CREATININE||1.4|mg/dL|0.6-1.2|H|||F
OBX|2|NM|3094-0^BUN||28|mg/dL|7-20|H|||F
OBX|3|TX|NOTE^Clinical Note||Renal insufficiency suspected.||||||F""",

    # Patient 6: Michael Brown - Hyperthyroidism
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412221400||ORU^R01|MSG006|P|2.5
PID|1||44006||BROWN^MICHAEL||19720930|M
OBR|1|ORD006|RES006|THYROID^Thyroid Panel|||202412221400
OBX|1|NM|3016-3^TSH||0.3|mIU/L|0.4-4.0|L|||F
OBX|2|NM|3053-6^FREE_T4||2.1|ng/dL|0.8-1.8|H|||F""",

    # Patient 7: Emily Davis - Liver (Hepatic)
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412211100||ORU^R01|MSG007|P|2.5
PID|1||33007||DAVIS^EMILY||19950615|F
OBR|1|ORD007|RES007|LFT^Liver Function Tests|||202412211100
OBX|1|NM|1742-6^ALT||52|U/L|7-35|H|||F
OBX|2|NM|1920-8^AST||48|U/L|10-40|H|||F""",

    # Patient 8: David Martinez - Heart Attack (Cardiac)
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412201630||ORU^R01|MSG008|P|2.5
PID|1||22008||MARTINEZ^DAVID||19580403|M
OBR|1|ORD008|RES008|CARDIAC^Cardiac Markers|||202412201630
OBX|1|NM|10839-9^TROPONIN_I||0.08|ng/mL|0.00-0.04|HH|||F
OBX|2|NM|2157-6^CK_MB||8.5|ng/mL|0.0-5.0|H|||F
OBX|3|TX|NOTE^Clinical Note||CRITICAL: Myocardial Infarction indicated.||||||F""",

    # Patient 9: Barbara Gordon - Severe Hypertension (Vitals)
    """MSH|^~\\&|HIS|MedCenter|LIS|VITALS|202412270815||ORU^R01|MSG009|P|2.5
PID|1||10009||GORDON^BARBARA||19600101|F
OBR|1|ORD009|RES009|8716-3^VITAL SIGNS|||202412270815
OBX|1|NM|8480-6^SYSTOLIC_BP||160|mmHg|90-120|HH|||F
OBX|2|NM|8462-4^DIASTOLIC_BP||98|mmHg|60-80|H|||F
OBX|3|NM|8867-4^HEART_RATE||88|bpm|60-100|N|||F
OBX|4|TX|NOTE^Clinical Note||Uncontrolled Hypertension. Patient non-compliant with meds.||||||F""",

    # Patient 10: Thomas Anderson - Sepsis Alert
    """MSH|^~\\&|HIS|MedCenter|LIS|VITALS|202412271845||ORU^R01|MSG010|P|2.5
PID|1||10010||ANDERSON^THOMAS||19850913|M
OBR|1|ORD010|RES010|8716-3^VITAL SIGNS|||202412271845
OBX|1|NM|8310-5^BODY_TEMP||103.2|degF|97.0-99.0|H|||F
OBX|2|NM|8867-4^HEART_RATE||115|bpm|60-100|H|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||92|mmHg|90-120|L|||F
OBX|4|NM|2708-6^O2_SAT||91|%|95-100|L|||F
OBX|5|TX|NOTE^Clinical Note||POSSIBLE SEPSIS: Fever + Tachycardia + Hypotension. Protocol initiated.||||||F"""
]

def seed_database(verbose: bool = True) -> int:
    """
    Insert sample messages into the database.
    """
    if verbose:
        print("Seeding database with sample data...")
    
    # Ensure DB is ready
    init_db()
    
    success_count = 0
    for i, hl7_text in enumerate(SAMPLE_MESSAGES, 1):
        try:
            # Process without LLM to be fast
            run_oru_pipeline(hl7_text, use_llm=False)
            if verbose:
                print(f"  [OK] Seeded message {i}/{len(SAMPLE_MESSAGES)}")
            success_count += 1
        except Exception as e:
            if verbose:
                print(f"  [FAIL] Failed message {i}: {e}")
                
    return success_count


if __name__ == "__main__":
    seed_database()
