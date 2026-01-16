# app/seed.py
from typing import List
from .agent import run_oru_pipeline
from .db import init_db

# Sample HL7 messages with various clinical scenarios
SAMPLE_MESSAGES: List[str] = [
    # Patient 1: John Smith - Elevated glucose (matches hero visual)
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412271200||ORU^R01|MSG001|P|2.5
PID|1||99001||SMITH^JOHN||19800515|M
OBR|1|ORD001|RES001|CBC^Complete Blood Count|||202412271200
OBX|1|NM|2345-7^GLUCOSE||105|mg/dL|70-100|N|||F
OBX|2|NM|718-7^HEMOGLOBIN||14.2|g/dL|13.5-17.5|N|||F
OBX|3|NM|6690-2^WBC||7200|/uL|4500-11000|N|||F
OBX|4|TX|NOTE^Clinical Note||Patient reports non-fasting status. Glucose slightly elevated but consistent with post-prandial state.||||||F""",

    # Patient 2: Jane Doe - Multiple abnormals (anemia + infection signs)
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412261430||ORU^R01|MSG002|P|2.5
PID|1||88002||DOE^JANE||19750322|F
OBR|1|ORD002|RES002|CBC^Complete Blood Count|||202412261430
OBX|1|NM|718-7^HEMOGLOBIN||9.2|g/dL|12.0-16.0|L|||F
OBX|2|NM|6690-2^WBC||12500|/uL|4500-11000|H|||F
OBX|3|NM|789-8^RBC||3.8|10*6/uL|4.0-5.5|L|||F
OBX|4|NM|787-2^MCV||82|fL|80-100|N|||F
OBX|5|TX|NOTE^Clinical Note||Microscopic examination reveals hypochromic microcytic red blood cells. Suggestive of iron deficiency anemia. Recommend follow-up iron studies.||||||F""",

    # Patient 3: Mary Wilson - Full CBC normal
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412251015||ORU^R01|MSG003|P|2.5
PID|1||77003||WILSON^MARY||19901108|F
OBR|1|ORD003|RES003|CBC^Complete Blood Count|||202412251015
OBX|1|NM|718-7^HEMOGLOBIN||13.8|g/dL|12.0-16.0|N|||F
OBX|2|NM|6690-2^WBC||6800|/uL|4500-11000|N|||F
OBX|3|NM|789-8^RBC||4.5|10*6/uL|4.0-5.5|N|||F
OBX|4|NM|777-3^PLATELETS||245000|/uL|150000-400000|N|||F
OBX|5|NM|787-2^MCV||88|fL|80-100|N|||F
OBX|6|TX|NOTE^Clinical Note||All parameters within normal limits. No further action required.||||||F""",

    # Patient 4: Robert Chen - Lipid panel with high cholesterol
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412240900||ORU^R01|MSG004|P|2.5
PID|1||66004||CHEN^ROBERT||19650714|M
OBR|1|ORD004|RES004|LIPID^Lipid Panel|||202412240900
OBX|1|NM|2093-3^CHOLESTEROL||245|mg/dL|0-200|H|||F
OBX|2|NM|2571-8^TRIGLYCERIDES||180|mg/dL|0-150|H|||F
OBX|3|NM|2085-9^HDL||42|mg/dL|40-60|N|||F
OBX|4|NM|13457-7^LDL||165|mg/dL|0-100|H|||F
OBX|5|TX|NOTE^Clinical Note||Lipid profile significantly elevated. Risk stratification recommends lifestyle modification and consideration of statin therapy.||||||F""",

    # Patient 5: Sarah Johnson - Metabolic panel with kidney concern
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412230830||ORU^R01|MSG005|P|2.5
PID|1||55005||JOHNSON^SARAH||19880229|F
OBR|1|ORD005|RES005|BMP^Basic Metabolic Panel|||202412230830
OBX|1|NM|2345-7^GLUCOSE||92|mg/dL|70-100|N|||F
OBX|2|NM|2160-0^CREATININE||1.4|mg/dL|0.6-1.2|H|||F
OBX|3|NM|3094-0^BUN||28|mg/dL|7-20|H|||F
OBX|4|NM|2951-2^SODIUM||140|mEq/L|136-145|N|||F
OBX|5|NM|2823-3^POTASSIUM||4.2|mEq/L|3.5-5.0|N|||F
OBX|6|TX|NOTE^Clinical Note||Elevated BUN/Creatinine ratio suggests pre-renal azotemia or possible early renal insufficiency. Recommend hydration and re-test in 2 weeks.||||||F""",

    # Patient 6: Michael Brown - Thyroid panel
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412221400||ORU^R01|MSG006|P|2.5
PID|1||44006||BROWN^MICHAEL||19720930|M
OBR|1|ORD006|RES006|THYROID^Thyroid Panel|||202412221400
OBX|1|NM|3016-3^TSH||0.3|mIU/L|0.4-4.0|L|||F
OBX|2|NM|3053-6^FREE_T4||2.1|ng/dL|0.8-1.8|H|||F
OBX|3|NM|3051-0^FREE_T3||4.8|pg/mL|2.3-4.2|H|||F
OBX|4|TX|NOTE^Clinical Note||TSH suppressed with elevated T4/T3 consistent with primary hyperthyroidism. Endocrinology referral advised.||||||F""",

    # Patient 7: Emily Davis - Liver function tests
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412211100||ORU^R01|MSG007|P|2.5
PID|1||33007||DAVIS^EMILY||19950615|F
OBR|1|ORD007|RES007|LFT^Liver Function Tests|||202412211100
OBX|1|NM|1742-6^ALT||52|U/L|7-35|H|||F
OBX|2|NM|1920-8^AST||48|U/L|10-40|H|||F
OBX|3|NM|1975-2^BILIRUBIN_TOTAL||0.9|mg/dL|0.1-1.2|N|||F
OBX|4|NM|6768-6^ALP||85|U/L|44-147|N|||F
OBX|5|TX|NOTE^Clinical Note||Mild transaminitis observed. Patient denies alcohol use. Screen for viral hepatitis if persistence > 6 months.||||||F""",

    # Patient 8: David Martinez - Cardiac markers (critical)
    """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202412201630||ORU^R01|MSG008|P|2.5
PID|1||22008||MARTINEZ^DAVID||19580403|M
OBR|1|ORD008|RES008|CARDIAC^Cardiac Markers|||202412201630
OBX|1|NM|10839-9^TROPONIN_I||0.08|ng/mL|0.00-0.04|HH|||F
OBX|2|NM|33762-6^NT_proBNP||450|pg/mL|0-125|H|||F
OBX|3|NM|2157-6^CK_MB||8.5|ng/mL|0.0-5.0|H|||F
OBX|4|TX|NOTE^Clinical Note||CRITICAL VALUE: Troponin I elevated. Critical results called to and read back by Dr. S. Johnson at 16:45. Immediate cardiac intervention protocol activated.||||||F""",
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
