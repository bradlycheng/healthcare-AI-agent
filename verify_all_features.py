import requests
import sys
import json

BASE_URL = "http://localhost:8080"

def log(msg, status="INFO"):
    print(f"[{status}] {msg}")

def fail(msg):
    log(msg, "FAIL")
    # Don't exit immediately, try to test other parts
    return False

def verify_dashboard():
    log("Testing Dashboard API...")
    try:
        resp = requests.get(f"{BASE_URL}/messages?limit=10")
        if resp.status_code != 200:
            return fail(f"Dashboard API failed: {resp.status_code}")
        
        data = resp.json()
        items = data.get("items", [])
        log(f"Fetched {len(items)} messages (Total: {data.get('total')})", "PASS")
        
        if len(items) == 0:
            return fail("No messages found to test with.")
            
        return items[0] # Return a sample message for further testing
    except Exception as e:
        return fail(f"Dashboard Exception: {e}")

def verify_patient_timeline(patient_id):
    log(f"Testing Patient Timeline for ID: {patient_id}...")
    try:
        resp = requests.get(f"{BASE_URL}/patients/{patient_id}/timeline")
        if resp.status_code != 200:
            return fail(f"Timeline API failed: {resp.status_code}")
            
        data = resp.json()
        visits = data.get("visits", [])
        log(f"Fetched {len(visits)} visits for patient", "PASS")
        
        # Verify Chart Data potential
        has_vitals = any(v.get('systolic_bp') or v.get('heart_rate') for v in visits)
        if has_vitals:
            log("Vital signs present for charting", "PASS")
        else:
            log("No vital signs found for charting", "WARN")
            
        return True
    except Exception as e:
        return fail(f"Timeline Exception: {e}")

def verify_ai_summary(patient_id):
    log(f"Testing AI Summary for ID: {patient_id}...")
    try:
        # AI Summary can be slow, set timeout
        resp = requests.get(f"{BASE_URL}/patients/{patient_id}/summary", timeout=30)
        
        if resp.status_code == 200:
            summary = resp.json().get("summary", "")
            if len(summary) > 10:
                log("AI Summary generated successfully", "PASS")
                # print(f"   Summary Preview: {summary[:100]}...")
            else:
                return fail("AI Summary empty")
        else:
            return fail(f"AI Summary API failed: {resp.status_code}")
            
    except Exception as e:
        return fail(f"AI Summary Exception: {e}")

def verify_alerts():
    log("Testing Clinical Alerts logic...")
    # We explicitly look for the 'David Danger' case or similar high troponin
    try:
        resp = requests.get(f"{BASE_URL}/messages?limit=50")
        items = resp.json().get("items", [])
        
        found_critical = False
        for item in items:
            # Need to fetch observations to see alert flag
            obs_resp = requests.get(f"{BASE_URL}/messages/{item['id']}/observations")
            if obs_resp.status_code == 200:
                observations = obs_resp.json().get("items", [])
                if any(o.get('alert_level') == 'CRITICAL' for o in observations):
                    found_critical = True
                    log(f"Found CRITICAL alert for Patient {item['patient_id']}", "PASS")
                    break
        
        if not found_critical:
            log("No CRITICAL alerts found (Did you trigger the test case?)", "WARN")
            
    except Exception as e:
        return fail(f"Alert Check Exception: {e}")

def main():
    print("=== STARTING FULL SYSTEM VERIFICATION ===")
    
    # 1. Dashboard
    sample_msg = verify_dashboard()
    if not sample_msg:
        print("Aborting: Dashboard seems empty/broken.")
        sys.exit(1)
        
    patient_id = sample_msg.get('patient_id')
    
    # 2. Patient Timeline
    if patient_id:
        verify_patient_timeline(patient_id)
        
        # 3. AI Summary (Only run if we have a valid patient)
        verify_ai_summary(patient_id)
    else:
        fail("No patient ID in sample message, skipping Timeline/AI tests.")

    # 4. Alerts
    verify_alerts()
    
    print("=== VERIFICATION COMPLETE ===")

if __name__ == "__main__":
    main()
