
import requests
import time
import json
import sys

BASE_URL = "http://localhost:8082"

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def check_health():
    try:
        r = requests.get(f"{BASE_URL}/health")
        if r.status_code == 200 and r.json().get("status") == "ok":
            log("Health Check Passed", "PASS")
            return True
        else:
            log(f"Health Check Failed: {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Health Check Error: {e}", "FAIL")
        return False

def test_reset():
    log("Resetting Database...", "STEP")
    r = requests.delete(f"{BASE_URL}/messages")
    if r.status_code == 204:
        log("Database Reset", "PASS")
    else:
        log(f"Database Reset Failed: {r.status_code}", "FAIL")

def test_parse_hl7():
    log("Parsing HL7 Message...", "STEP")
    hl7_msg = "MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_E2E|P|2.5\rPID|1||99999||TEST^E2E||19800101|M\rOBR|1|ORD1|RES1|PANEL1|||202401201200\rOBX|1|NM|GLUCOSE||120|mg/dL|70-100|H|||F"
    
    payload = {
        "hl7_text": hl7_msg,
        "use_llm": True, 
        "persist": True
    }
    
    try:
        r = requests.post(f"{BASE_URL}/oru/parse", json=payload)
        if r.status_code == 200:
            data = r.json()
            if data["patient"]["first_name"] == "E2E":
                log("HL7 Parse & Persist", "PASS")
                return True
            else:
                 log(f"HL7 Parse Mismatch: {data}", "FAIL")
        else:
            log(f"HL7 Parse Failed: {r.text}", "FAIL")
    except Exception as e:
        log(f"HL7 Parse Error: {e}", "FAIL")
    return False

def test_agent_query():
    log("Testing Agent Query...", "STEP")
    # Wait for data to settle
    time.sleep(1)
    
    payload = {
        "question": "Does TEST E2E have high glucose?",
        "history": []
    }
    
    try:
        r = requests.post(f"{BASE_URL}/api/query", json=payload)
        if r.status_code == 200:
            data = r.json()
            if data["success"] and "high" in data["answer"].lower():
                log(f"Agent Answered: {data['answer']}", "PASS")
            else:
                log(f"Agent Wrong Answer: {data}", "FAIL")
        else:
            log(f"Agent Query Failed: {r.text}", "FAIL")
    except Exception as e:
         log(f"Agent Query Error: {e}", "FAIL")

def test_patient_list():
    log("Testing Patient List...", "STEP")
    r = requests.get(f"{BASE_URL}/patients")
    if r.status_code == 200:
        data = r.json()
        found = any(p["last_name"] == "E2E" for p in data["patients"])
        if found:
            log("Patient List contains TEST E2E", "PASS")
        else:
            log(f"Patient E2E not found in list: {data}", "FAIL")
    else:
        log(f"Patient List Failed: {r.status_code}", "FAIL")

def run_all():
    log(f"Starting API E2E Test against {BASE_URL}")
    if not check_health():
        log("Server not running or unhealthy. Aborting.", "CRITICAL")
        sys.exit(1)
        
    test_reset()
    if test_parse_hl7():
        test_patient_list()
        test_agent_query()
    else:
        log("Skipping dependent tests due to Parse failure.", "WARN")

if __name__ == "__main__":
    run_all()
