"""Test the demo sample from index.html"""
import requests
import json

# The demo sample from index.html
HL7_SAMPLE = """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_CARDIAC|P|2.5
PID|1||12345||SMITH^JOHN||19750315|M
OBR|1|ORD456|RES456|CARD-PANEL^Cardiac Panel|||202401201200
OBX|1|NM|49563-0^TROPONIN I||0.12|ng/mL|0.00-0.04|HH|||F
OBX|2|NM|2157-6^CK-MB||8.5|ng/mL|0.0-5.0|H|||F
OBX|3|TX|NOTE^Clinical Note||50 y/o male presenting with crushing chest pain radiating to left arm x 2 hours. Diaphoretic, BP 160/95, HR 110, SpO2 94% on room air. History of HTN and hyperlipidemia. ECG shows ST elevation in leads V1-V4. Suspect STEMI. Cardiology consult requested. Started on aspirin, heparin, nitroglycerin drip.||||||F"""

URL = "http://localhost:8080/oru/parse"

print("=== TESTING DEMO SAMPLE (WITH AI) ===\n")

try:
    # Test with LLM enabled
    resp = requests.post(URL, json={
        "hl7_text": HL7_SAMPLE,
        "use_llm": True,
        "persist": False
    }, timeout=60)
    
    if resp.status_code == 200:
        data = resp.json()
        
        print("--- PATIENT ---")
        patient = data.get("patient", {})
        print(f"  Name: {patient.get('first_name')} {patient.get('last_name')}")
        print(f"  ID: {patient.get('id')}")
        
        print("\n--- CLINICAL SUMMARY ---")
        print(f"  {data.get('clinical_summary', 'N/A')[:200]}...")
        
        print("\n--- OBSERVATIONS ---")
        observations = data.get("structured_observations", [])
        print(f"  Total: {len(observations)}")
        has_glucose = False
        for obs in observations:
            source = obs.get("source", "?")
            name = obs.get("display", obs.get("code", "?"))
            value = obs.get("value", "?")
            
            # Check for Glucose
            if "GLUCOSE" in str(name).upper():
                has_glucose = True
                print(f"  [{source}] {name}: {value} [!!! GLUCOSE HALLUCINATED !!!]")
            else:
                print(f"  [{source}] {name}: {value}")
        
        if not has_glucose:
            print("\n[PASS] NO Glucose Hallucination")
        else:
            print("\n[FAIL] Glucose Hallucination Present")
            
    else:
        print(f"ERROR: HTTP {resp.status_code}")
        print(resp.text[:500])

except Exception as e:
    print(f"ERROR: {e}")
