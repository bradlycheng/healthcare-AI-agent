
import requests
import json
import sys

# URL of the local API
API_URL = "http://localhost:8080/oru/parse"

# Payload reconstruction from screenshot
Payload = """MSH|^~\\&|HIS|MedCenter|LIS|LAB|202401201200||ORU^R01|MSG_REPRO|P|2.5
PID|1||12345||TEST^PATIENT||19800101|M
OBR|1|ORD123|RES123|CBC^Complete Blood Count|||202401201200
OBX|1|NM|718-7^HEMOGLOBIN||14.2|g/dL|13.5-17.5|N|||F
OBX|2|NM|6690-2^WBC||7200|/uL|4500-11000|N|||F
OBX|3|TX|NOTE^Clinical Note||Patient reports recent fasting blood glucose of 145 mg/dL from home monitor. History of hypertension, BP 138/88 at last visit..||||||F"""

from app.agent import run_oru_pipeline

def test_reproduction():
    print("Testing Payload from Screenshot (Direct Call)...")
    
    # Run pipeline directly to see stdout/stderr
    result = run_oru_pipeline(Payload, use_llm=True, persist=False)
    
    summary = result.get("clinical_summary", "")
    print("\n--- SUMMARY RECEIVED ---")
    print(summary)
    print("------------------------")
    
    # Check for "Is" vs "Has a value of"
    # Basic summary: "Clinical Note (NOTE) has a value of..."
    # AI summary usually interprets it.
    
    if "has a value of " in summary and "Patient reports" in summary:
        print("[FAIL] This is the BASIC summary. LLM failed or was skipped.")
    else:
        print("[SUCCESS] This implies LLM modification (or different format).")

if __name__ == "__main__":
    test_reproduction()
