import requests
import json

# The new enhanced sample HL7 from index.html
HL7_MESSAGE = """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_CARDIAC|P|2.5
PID|1||CARDIAC-001||DANGER^DAVID||19750315|M
OBR|1|ORD456|RES456|CARD-PANEL^Cardiac Panel|||202401201200
OBX|1|NM|49563-0^TROPONIN I||0.12|ng/mL|0.00-0.04|HH|||F
OBX|2|NM|2157-6^CK-MB||8.5|ng/mL|0.0-5.0|H|||F
OBX|3|TX|NOTE^Clinical Note||50 y/o male presenting with crushing chest pain radiating to left arm x 2 hours. Diaphoretic, BP 160/95, HR 110, SpO2 94% on room air. History of HTN and hyperlipidemia. ECG shows ST elevation in leads V1-V4. Suspect STEMI. Cardiology consult requested. Started on aspirin, heparin, nitroglycerin drip.||||||F"""

URL = "http://localhost:8080/oru/parse"

print("=== Testing Enhanced Cardiac Sample ===")
print("Patient: DANGER, DAVID (CARDIAC-001)")
print()

try:
    resp = requests.post(URL, json={"hl7_text": HL7_MESSAGE, "persist": False, "use_llm": True}, timeout=60)
    
    if resp.status_code == 200:
        data = resp.json()
        
        print("--- CLINICAL SUMMARY (AI Generated) ---")
        print(data.get("clinical_summary", "No summary"))
        print()
        
        print("--- OBSERVATIONS EXTRACTED ---")
        observations = data.get("structured_observations", [])
        for obs in observations:
            source = obs.get("source", "?")
            name = obs.get("display", obs.get("code", "?"))
            value = obs.get("value", "?")
            unit = obs.get("unit", "")
            flag = obs.get("flag", "")
            alert = obs.get("alert_level", "")
            
            alert_marker = f" [**{alert}**]" if alert else ""
            flag_marker = f" ({flag})" if flag else ""
            
            print(f"  [{source}] {name}: {value} {unit}{flag_marker}{alert_marker}")
        
        # Count AI-extracted observations
        ai_count = sum(1 for o in observations if o.get("source") == "AI")
        hl7_count = sum(1 for o in observations if o.get("source") == "HL7")
        print()
        print(f"Summary: {hl7_count} from HL7, {ai_count} from AI extraction")
        
    else:
        print(f"[FAIL] API returned status {resp.status_code}")
        print(resp.text)

except Exception as e:
    print(f"[ERROR] {e}")
