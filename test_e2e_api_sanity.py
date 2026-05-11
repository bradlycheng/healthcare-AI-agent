import requests
import json
import time
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8080/"

def test_analyze():
    print("\n[Testing POST /oru/parse]")
    payload = {
        "hl7_text": "MSH|^~\\&|LAB|CLINIC|APP|HOSP|202305011030||ORU^R01|123|P|2.5.1\nPID|1||P001||SMITH^JOHN\nOBX|1|NM|2339-0^Glucose||105|mg/dL|70-99|H|||F",
        "persist": True
    }
    res = requests.post(BASE_URL + "oru/parse", json=payload)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        print(f"Response: {json.dumps(res.json(), indent=2)[:200]}...")
    return res.status_code == 200

def test_query_deep():
    print("\n[Testing POST /api/query - DEEP MODE]")
    payload = {
        "question": "What is John Smith's latest glucose?",
        "reasoning_depth": "deep"
    }
    res = requests.post(BASE_URL + "api/query", json=payload)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        data = res.json()
        print(f"Answer: {data.get('answer')}")
        print(f"Trace: {len(data.get('reasoning_trace', []))} steps")
    return res.status_code == 200

def test_reset():
    print("\n[Testing POST /admin/reset]")
    password = os.environ.get("ADMIN_PASSWORD")
    payload = {"password": password}
    res = requests.post(BASE_URL + "admin/reset", json=payload)
    print(f"Status: {res.status_code}")
    if res.status_code == 200:
        print(f"Response: {res.json().get('message')}")
    return res.status_code == 200

if __name__ == "__main__":
    print("Beginning E2E API Sanity Check...")
    results = {
        "Analyze": test_analyze(),
        "Query (Deep)": test_query_deep(),
        "Reset": test_reset()
    }
    print("\nFinal Results:")
    for test, passed in results.items():
        print(f"{test}: {'PASS' if passed else 'FAIL'}")
