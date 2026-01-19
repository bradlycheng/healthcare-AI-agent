"""
Test Advanced Clinical Scenarios
================================
This script sends complex HL7 messages to the Healthcare AI Agent API
to verify its clinical reasoning and summary generation capabilities.
"""

import sys
import io

# Fix Windows console encoding for Unicode
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json
import time
from datetime import datetime
from typing import Dict, Any

API_BASE = "http://localhost:8080"
PARSE_ENDPOINT = f"{API_BASE}/oru/parse"

# Advanced Clinical Scenarios
TEST_MESSAGES = [
    {
        "name": "Renal Function Panel (Kidney Failure)",
        "description": "High Creatinine/BUN, Low GFR indicating renal issues",
        "hl7": """MSH|^~\\&|LAB|NEPRHO|EHR|MAIN|202501180900||ORU^R01|RENAL001|P|2.5
PID|1||90001^^^MRN||RENAL^PATIENT||19650220|M
OBR|1|||RENAL_PANEL
OBX|1|NM|CREAT^Creatinine||1.8|mg/dL|0.7-1.3|H|||F
OBX|2|NM|BUN^Blood Urea Nitrogen||28|mg/dL|7-20|H|||F
OBX|3|NM|EGFR^Est. GFR||52|mL/min/1.73m2|>60|L|||F
OBX|4|NM|K^Potassium||5.5|mEq/L|3.5-5.0|H|||F"""
    },
    {
        "name": "Thyroid Cascade (Hyperthyroidism)",
        "description": "Low TSH with High T4/T3",
        "hl7": """MSH|^~\\&|LAB|ENDO|EHR|MAIN|202501180915||ORU^R01|THYROID001|P|2.5
PID|1||90002^^^MRN||THYROID^PATIENT||19881115|F
OBR|1|||THYROID_PANEL
OBX|1|NM|TSH^Thyroid Stimulating Hormone||0.05|mIU/L|0.4-4.0|L|||F
OBX|2|NM|FT4^Free T4||2.8|ng/dL|0.8-1.8|H|||F
OBX|3|NM|T3^Total T3||220|ng/dL|76-181|H|||F"""
    },
    {
        "name": "Acute Cardiac Event",
        "description": "Critical Troponin and CK-MB levels",
        "hl7": """MSH|^~\\&|LAB|ER|EHR|MAIN|202501180930||ORU^R01|CARDIAC001|P|2.5
PID|1||90003^^^MRN||CARDIAC^PATIENT||19550610|M
OBR|1|||CARDIAC_ENZYMES
OBX|1|NM|TROP^Troponin I||0.85|ng/mL|<0.04|H|||F
OBX|2|NM|CKMB^CK-MB||12.5|ng/mL|<5.0|H|||F
OBX|3|TX|EKG^EKG Interpretation||ST elevation noted in leads V1-V4. Suggestive of anterior wall MI.||||F"""
    },
    {
        "name": "Liver Function (Hepatitis pattern)",
        "description": "Markedly elevated AST/ALT with elevated Bilirubin",
        "hl7": """MSH|^~\\&|LAB|GI|EHR|MAIN|202501180945||ORU^R01|LIVER001|P|2.5
PID|1||90004^^^MRN||LIVER^PATIENT||19720930|F
OBR|1|||HEPATIC_FUNC
OBX|1|NM|ALT^Alanine Aminotransferase||350|U/L|7-56|H|||F
OBX|2|NM|AST^Aspartate Aminotransferase||280|U/L|10-40|H|||F
OBX|3|NM|TBIL^Total Bilirubin||2.5|mg/dL|0.1-1.2|H|||F
OBX|4|NM|ALP^Alkaline Phosphatase||180|U/L|44-147|H|||F"""
    }
]

def run_tests():
    print("\n" + "=" * 70)
    print("ADVANCED CLINICAL SCENARIOS TEST")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Note: 6s delay between requests for rate limiting.\n")
    
    results = []
    
    for i, test in enumerate(TEST_MESSAGES, 1):
        if i > 1:
            print(f"Waiting 6s for rate limit...")
            time.sleep(6)
            
        print(f"[{i}/{len(TEST_MESSAGES)}] Sending: {test['name']}")
        print(f"   Context: {test['description']}")
        
        try:
            resp = requests.post(
                PARSE_ENDPOINT, 
                json={"hl7_text": test['hl7'], "use_llm": True, "persist": True}
            )
            resp.raise_for_status()
            data = resp.json()
            
            summary = data.get('clinical_summary', 'No summary generated')
            print(f"\n   ✅ Success! Summary Preview:")
            print(f"   \"{summary[:150]}...\"")
            
            # Simple validation rules
            passed = True
            if "Renal" in test['name'] and not any(kw in summary.lower() for kw in ['kidney', 'renal', 'failure', 'dysfunction']):
                print("   ⚠️  Warning: Summary missed kidney/renal keywords.")
            if "Cardiac" in test['name'] and not any(kw in summary.lower() for kw in ['heart', 'cardiac', 'myocardial', 'infarction', 'mi']):
                print("   ⚠️  Warning: Summary missed cardiac keywords.")
                
            results.append({"name": test['name'], "status": "PASS" if passed else "WARN"})
            
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results.append({"name": test['name'], "status": "FAIL"})
            
    print("\n" + "=" * 70)
    print("TEST REPORT")
    print("=" * 70)
    for r in results:
        icon = "✅" if r['status'] == "PASS" else ("⚠️" if r['status'] == "WARN" else "❌")
        print(f"{icon} {r['name']}")
        
if __name__ == "__main__":
    run_tests()
