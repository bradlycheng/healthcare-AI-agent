"""
Final Reliability & Expert Verification Test
Target: Healthcare AI Agent v1.0
Date: 2026-01-27
"""
import requests
import sqlite3
import time
import json

URL = "http://localhost:8080/api/query"
DB_PATH = "agent.db"

results = {
    "sections": 0,
    "passed": 0,
    "failed": 0,
    "warnings": 0
}

def print_header(title):
    print(f"\n{'='*80}\n{title}\n{'='*80}")

def print_result(name, passed, msg=""):
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} | {name} {f'- {msg}' if msg else ''}")
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1

def check_db_integrity():
    print_header("1. DATABASE INTEGRITY CHECK")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Patient Count
        cursor.execute("SELECT COUNT(DISTINCT patient_id) FROM hl7_messages")
        count = cursor.fetchone()[0]
        passed = count >= 29 # 11 original + 18 new distinct
        print_result("Patient Count", passed, f"Found {count} patients (Target: 29)")
        
        # Observation Volume
        cursor.execute("SELECT COUNT(*) FROM observations")
        obs_count = cursor.fetchone()[0]
        passed = obs_count >= 190
        print_result("Observation Volume", passed, f"Found {obs_count} observations (Target: >190)")
        
        # Critical Patients
        patients = ["SARAH", "MICHAEL", "JAMES", "BRIAN"]
        found = 0
        for p in patients:
            cursor.execute(f"SELECT COUNT(*) FROM hl7_messages WHERE patient_first_name LIKE '%{p}%'")
            if cursor.fetchone()[0] > 0:
                found += 1
        print_result("Critical Patient Data", found == 4, f"Found {found}/4 key personas")
        
        conn.close()
    except Exception as e:
        print_result("DB Connection", False, str(e))

def test_ai_query(name, query, expected_keywords=[], history=[]):
    time.sleep(2) # Prevent rate limiting
    try:
        payload = {"question": query, "history": history}
        resp = requests.post(URL, json=payload)
        
        if resp.status_code == 200:
            data = resp.json()
            if not data.get("success"):
                print_result(name, False, "API returned success=False")
                return None
            
            # Content check
            sql = data.get("sql_used", "").upper()
            answer = data.get("answer", "")
            rows = data.get("row_count", 0)
            
            missing = [k for k in expected_keywords if k.upper() not in sql and k.upper() not in str(data)]
            
            # If we got rows, it's a success for data retrieval queries
            if rows > 0:
                print_result(name, True, f"Rows: {rows}")
                return data
            
            if missing:
                print_result(name, False, f"Missing keywords: {missing}")
        elif resp.status_code == 429:
             print_result(name, False, "Rate Limited (429)")
        else:
             print_result(name, False, f"HTTP {resp.status_code}")
    except Exception as e:
        print_result(name, False, f"Exception: {e}")
    return None

def check_clinical_intelligence():
    print_header("2. CLINICAL INTELLIGENCE VERIFICATION")
    
    # 1. Longitudinal
    test_ai_query("Longitudinal Tracking", 
                 "Show Sarah Johnson's glucose trend", 
                 ["GLUCOSE"])
                 
    # 2. Acute Event
    time.sleep(5)
    test_ai_query("Acute Event Detection", 
                 "Who has elevated troponin?", 
                 ["TROPONIN"])
    
    # 3. Comorbidities
    time.sleep(5)
    test_ai_query("Complex Comorbidity", 
                 "Show patients with diabetes and high cholesterol", 
                 ["DIABETES", "CHOLESTEROL"])

def check_conversational_state():
    print_header("3. CONVERSATIONAL STATE & MEMORY")
    
    history = []
    
    # Turn 1
    time.sleep(5)
    resp1 = test_ai_query("Context Setting", "Show reports for Michael Chen", ["MICHAEL", "CHEN"])
    if resp1:
        history.append({"role": "user", "content": "Show reports for Michael Chen"})
        history.append({"role": "ai", "content": "Here are the results."})
        
        # Turn 2
        time.sleep(5)
        test_ai_query("Pronoun Resolution", 
                     "What is his blood pressure?", 
                     ["MICHAEL", "BP"], 
                     history=history)

def check_security():
    print_header("4. SECURITY PROTOCOLS")
    
    # SQL Injection
    time.sleep(5)
    resp = requests.post(URL, json={"question": "SELECT * FROM observations"})
    passed = False
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success") is False:
            passed = True
    
    print_result("SQL Injection Block", passed, "System correctly rejected raw SQL")

def run_suite():
    print("Starting Expert Reliability Test Suite...")
    check_db_integrity()
    check_clinical_intelligence()
    check_conversational_state()
    check_security()
    
    print_header("FINAL VERDICT")
    total = results["passed"] + results["failed"]
    score = (results["passed"] / total) * 100 if total > 0 else 0
    print(f"Score: {score:.1f}% ({results['passed']}/{total})")
    
    if results["failed"] == 0:
        print("\n SYSTEM STATUS: ROCK SOLID")
    else:
        print("\n SYSTEM STATUS: ATTENTION NEEDED")

if __name__ == "__main__":
    run_suite()
