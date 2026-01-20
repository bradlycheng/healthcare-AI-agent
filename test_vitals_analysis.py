
import requests
import json
import sys

# URL of the local API
API_URL = "http://localhost:8080/oru/parse"

# Patient 9: Barbara Gordon - Severe Hypertension
Payload_Hypertension = """MSH|^~\\&|HIS|MedCenter|LIS|VITALS|202412270815||ORU^R01|MSG009|P|2.5
PID|1||10009||GORDON^BARBARA||19600101|F
OBR|1|ORD009|RES009|8716-3^VITAL SIGNS|||202412270815
OBX|1|NM|8480-6^SYSTOLIC_BP||160|mmHg|90-120|HH|||F
OBX|2|NM|8462-4^DIASTOLIC_BP||98|mmHg|60-80|H|||F
OBX|3|NM|8867-4^HEART_RATE||88|bpm|60-100|N|||F
OBX|4|TX|NOTE^Clinical Note||Uncontrolled Hypertension. Patient non-compliant with meds.||||||F"""

# Patient 10: Thomas Anderson - Sepsis Alert
Payload_Sepsis = """MSH|^~\\&|HIS|MedCenter|LIS|VITALS|202412271845||ORU^R01|MSG010|P|2.5
PID|1||10010||ANDERSON^THOMAS||19850913|M
OBR|1|ORD010|RES010|8716-3^VITAL SIGNS|||202412271845
OBX|1|NM|8310-5^BODY_TEMP||103.2|degF|97.0-99.0|H|||F
OBX|2|NM|8867-4^HEART_RATE||115|bpm|60-100|H|||F
OBX|3|NM|8480-6^SYSTOLIC_BP||92|mmHg|90-120|L|||F
OBX|4|NM|2708-6^O2_SAT||91|%|95-100|L|||F
OBX|5|TX|NOTE^Clinical Note||POSSIBLE SEPSIS: Fever + Tachycardia + Hypotension. Protocol initiated.||||||F"""

def test_vitals_scenario(name, hl7_text, expected_terms):
    print(f"\nTesting Scenario: {name}")
    print("-" * 50)
    
    payload = {
        "hl7_text": hl7_text,
        "use_llm": True,
        "persist": False # Don't save to DB, just test logic
    }
    
    try:
        response = requests.post(API_URL, json=payload)
        
        if response.status_code != 200:
            print(f"FAILED: API returned {response.status_code}")
            print(response.text)
            return False
            
        data = response.json()
        summary = data.get("clinical_summary", "")
        print(f"AI Summary: {summary}")
        
        missing = [term for term in expected_terms if term.lower() not in summary.lower()]
        
        if missing:
            print(f"FAILED: Summary missing expected terms: {missing}")
            return False
        
        print("PASSED:AI correctly identified the condition.")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def run_tests():
    print("Running Vitals & Clinical Logic Verification...")
    
    import time

    # Test 1: Hypertension
    p1 = test_vitals_scenario(
        "Severe Hypertension (Barbara Gordon)", 
        Payload_Hypertension, 
        ["Hypertension", "BP", "High"] 
    )
    
    # Wait for rate limit (5s cooldown)
    print("Waiting 6 seconds for rate limit cooldown...")
    time.sleep(6)

    # Test 2: Sepsis
    p2 = test_vitals_scenario(
        "Sepsis Alert (Thomas Anderson)", 
        Payload_Sepsis, 
        ["Sepsis", "Fever", "Hypotension"]
    )
    
    if p1 and p2:
        print("\nALL VITALS TESTS PASSED [OK]")
        sys.exit(0)
    else:
        print("\nSOME VITALS TESTS FAILED [FAIL]")
        sys.exit(1)

if __name__ == "__main__":
    run_tests()
