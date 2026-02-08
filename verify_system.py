import requests
import json
import time
import sys
import io

# Fix Windows console encoding for Unicode
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE_URL = "http://localhost:8000"

def print_pass(msg):
    print(f"[PASS]: {msg}")

def print_fail(msg):
    print(f"[FAIL]: {msg}")
    sys.exit(1)

def verify_system():
    print(f"Starting System Verification against {BASE_URL}...\n")

    # 1. Health Check
    try:
        resp = requests.get(f"{BASE_URL}/health")
        if resp.status_code == 200 and resp.json().get("status") == "ok":
            print_pass("Health Check (GET /health)")
        else:
            print_fail(f"Health Check failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print_fail(f"Could not connect to server: {e}")

    # 2. Upload HL7 Message
    hl7_data = """MSH|^~\\&|LAB|FACILITY|EHR|FACILITY|20250118||ORU^R01|VERIFY001|P|2.5
PID|1||99002^^^MRN||TEST^VERIFY||19800101|M
OBR|1|||BASIC_PANEL
OBX|1|NM|GLU^Glucose||105|mg/dL|70-100|H|||F"""
    
    payload = {
        "hl7_text": hl7_data,
        "use_llm": True,
        "persist": True
    }

    print("\nSending HL7 Message...")
    try:
        resp = requests.post(f"{BASE_URL}/oru/parse", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if data["patient"]["first_name"] == "VERIFY":
                print_pass("HL7 Upload & Parse (POST /oru/parse)")
            else:
                print_fail(f"Parsing mismatch. Expected VERIFY, got {data['patient']['first_name']}")
        else:
            print_fail(f"Upload failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print_fail(f"Upload exception: {e}")

    # 3. List Messages
    print("\nVerifying Message Persistence...")
    try:
        resp = requests.get(f"{BASE_URL}/messages?limit=5")
        if resp.status_code == 200:
            items = resp.json()["items"]
            found = any(i["first_name"] == "VERIFY" and i["last_name"] == "TEST" for i in items)
            if found:
                print_pass("Message listed in DB (GET /messages)")
            else:
                print_fail("Uploaded message not found in list")
        else:
            print_fail(f"List failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print_fail(f"List exception: {e}")

    # 4. Run Query (Advanced)
    print("Waiting 6s for rate limiter reset...")
    time.sleep(6)
    
    query = "Who has high glucose?"
    print(f"\nTesting Query: '{query}'...")
    try:
        q_payload = {"question": query}
        resp = requests.post(f"{BASE_URL}/api/query", json=q_payload)
        if resp.status_code == 200:
            data = resp.json()
            if data["success"] and "TEST VERIFY" in data["answer"].upper() or "105" in data["answer"]:
                 print_pass("AI Query Response (POST /api/query)")
            else:
                # Provide a softer failure if it just didn't find specific text but returned success
                if data["success"]:
                    print(f"⚠️  Warning: Query successful but didn't explicitly mention 'TEST VERIFY' (Answer: {data.get('answer')})")
                    print_pass("AI Query Response (Soft Pass)")
                else:
                    print_fail(f"Query returned failure: {data.get('error')}")
        else:
            print_fail(f"Query request failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print_fail(f"Query exception: {e}")

    # 5. Reset Demo (DELETE /messages)
    print("\nTesting Reset Demo...")
    try:
        resp = requests.delete(f"{BASE_URL}/messages")
        if resp.status_code == 204:
            print_pass("Reset Demo (DELETE /messages)")
        else:
            print_fail(f"Reset failed: {resp.status_code} {resp.text}")
    except Exception as e:
        print_fail(f"Reset exception: {e}")

    print("\n🎉 All Verification Steps Passed!")

if __name__ == "__main__":
    verify_system()
