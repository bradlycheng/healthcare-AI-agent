import requests
import json

# The new sample HL7 from index.html
HL7_MESSAGE = """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_CARDIAC|P|2.5
PID|1||CARDIAC-001||DANGER^DAVID||19750315|M
OBR|1|ORD456|RES456|CARD-PANEL^Cardiac Panel|||202401201200
OBX|1|NM|49563-0^TROPONIN I||0.12|ng/mL|0.00-0.04|HH|||F
OBX|2|NM|2157-6^CK-MB||8.5|ng/mL|0.0-5.0|H|||F
OBX|3|TX|NOTE^Clinical Note||CRITICAL: Elevated cardiac markers. Rule out acute MI.||||||F"""

URL = "http://localhost:8080/oru/parse"

print("=== Testing New Cardiac Alert Sample ===")
print(f"Patient: DANGER, DAVID (CARDIAC-001)")
print(f"Troponin I: 0.12 ng/mL (Normal: 0.00-0.04)")
print()

try:
    resp = requests.post(URL, json={"hl7_text": HL7_MESSAGE, "persist": False, "use_llm": False}, timeout=10)
    
    if resp.status_code == 200:
        data = resp.json()
        observations = data.get("structured_observations", [])
        
        found_critical = False
        for obs in observations:
            if obs.get("alert_level") == "CRITICAL":
                found_critical = True
                print(f"[PASS] CRITICAL ALERT TRIGGERED!")
                print(f"  Test: {obs.get('display')}")
                print(f"  Value: {obs.get('value')} {obs.get('unit')}")
                print(f"  Message: {obs.get('alert_message')}")
                break
        
        if not found_critical:
            print("[WARN] No CRITICAL alert detected. Checking for flags...")
            for obs in observations:
                if obs.get("flag") in ["H", "HH", "L", "LL"]:
                    print(f"  - {obs.get('display')}: {obs.get('value')} ({obs.get('flag')})")
    else:
        print(f"[FAIL] API returned status {resp.status_code}")
        print(resp.text)

except Exception as e:
    print(f"[ERROR] {e}")
