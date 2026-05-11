import requests
import sys
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8080"

def log(btn, status, msg=""):
    icon = "[PASS]" if status == "PASS" else "[FAIL]"
    print(f"{icon} Button '{btn}': {status} {msg}")

def test_buttons():
    print("=== UI BUTTON SIMULATION TEST ===")
    
    # 1. "Analyze (Preview)" Button
    # Logic: POST /oru/parse
    try:
        hl7 = "MSH|^~\\&|TEST|TEST|TEST|TEST|20250101||ORU^R01|MSG001|P|2.5\rPID|1||12345||TEST^PATIENT||19800101|M"
        resp = requests.post(f"{BASE_URL}/oru/parse", json={"hl7_text": hl7, "use_llm": False, "persist": False})
        if resp.status_code == 200:
            log("Analyze (Preview)", "PASS", "(Parsed HL7)")
        else:
            log("Analyze (Preview)", "FAIL", f"Status {resp.status_code}")
    except Exception as e:
        log("Analyze (Preview)", "FAIL", str(e))

    # 2. "Confirm & Save" Button
    # Logic: POST /messages (with observations)
    try:
        # Minimal payload mimicking what JS constructs
        payload = {
            "patient": {"id": "12345", "first_name": "TEST", "last_name": "PATIENT", "dob": "19800101", "sex": "M"},
            "structured_observations": [{"code": "123", "value": 100, "unit": "mg/dL", "source": "MANUAL"}],
            "raw_hl7": hl7,
            "clinical_summary": "Test summary",
            "fhir_bundle": {}
        }
        resp = requests.post(f"{BASE_URL}/messages", json=payload)
        if resp.status_code == 200:
            log("Confirm & Save", "PASS", "(Saved to DB)")
        else:
            log("Confirm & Save", "FAIL", f"Status {resp.status_code}: {resp.text}")
    except Exception as e:
        log("Confirm & Save", "FAIL", str(e))

    # 3. "AI Assistant Submit" Button
    # Logic: POST /api/query
    try:
        resp = requests.post(f"{BASE_URL}/api/query", json={"question": "Show all patients"})
        if resp.status_code == 429:
             log("AI Submit", "PASS", "(Rate Limited - Expected)")
        elif resp.status_code == 200:
             log("AI Submit", "PASS", "(Query processed)")
        else:
             log("AI Submit", "FAIL", f"Status {resp.status_code}")
    except Exception as e:
        log("AI Submit", "FAIL", str(e))

    # 4. "Reset Demo" Button (Dashboard)
    # Logic: JS calls DELETE /messages (verify this path!)
    # We suspect this might be wrong, so let's test BOTH paths
    
    # Path A: The one in dashboard.js (NOW FIXED)
    print("\nTesting Dashboard 'Reset Demo' Path (POST /admin/reset)...")
    password = os.environ.get("ADMIN_PASSWORD")
    resp_reset = requests.post(f"{BASE_URL}/admin/reset", json={"password": password})
    if resp_reset.status_code == 200 or resp_reset.status_code == 409:
        log("Reset Demo (JS Path)", "PASS", "Database reset initiated")
    else:
        log("Reset Demo (JS Path)", "FAIL", f"Status {resp_reset.status_code}")

    # Path B: The correct API path
    print("\nTesting Correct Admin Path (POST /admin/reset)...")
    resp_reset = requests.post(f"{BASE_URL}/admin/reset", json={"password": password})
    if resp_reset.status_code == 200:
         log("Admin Reset Endpoint", "PASS", "Database successfully reset")
    else:
         log("Admin Reset Endpoint", "FAIL", f"Status {resp_reset.status_code}")

if __name__ == "__main__":
    test_buttons()
