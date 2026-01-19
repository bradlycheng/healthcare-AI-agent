"""
Test Noisy/Messy Clinical Messages
==================================
This script sends HL7 messages with typos, slang, bad grammar, and unstructured text 
to verify if the AI agent can still extract meaningful clinical summaries.
"""

import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json
import time
from datetime import datetime

API_BASE = "http://localhost:8080"
PARSE_ENDPOINT = f"{API_BASE}/oru/parse"

TEST_MESSAGES = [
    {
        "name": "Doctor's Notes with Typos (Cardiac)",
        "description": "Notes contain severe typos ('prain', 'palps') and shorthand.",
        "hl7": """MSH|^~\\&|ER|HOSP|EHR|MAIN|202501181200||ORU^R01|NOISY01|P|2.5
PID|1||99901^^^MRN||MESSY^TYPO||19800101|M
OBR|1|||NOTES
OBX|1|TX|NOTE^Clinical Note||Pt cmplains of chest prain radiating to left arm. Says feels like 'elphant sitting on chest'. Has hx of HTN and diabtes. Denies sob but has palps.||||F"""
    },
    {
        "name": "Unstructured Vitals with Slang",
        "description": "Vitals mixed into text with slang ('tachy', 'satting').",
        "hl7": """MSH|^~\\&|TRIAGE|ER|EHR|MAIN|202501181215||ORU^R01|NOISY02|P|2.5
PID|1||99902^^^MRN||SLANG^USER||19950505|F
OBR|1|||TRIAGE_NOTE
OBX|1|TX|VITALS^Triage Vitals||Pt is super tachy hr 130s. Satting 88% on RA. BP kinda soft 90/60. Looks pale and diaphoretic. Needs fluids asap.||||F"""
    },
    {
        "name": "Mixed Case and Bad Grammar",
        "description": "Inconsistent casing and run-on sentences.",
        "hl7": """MSH|^~\\&|LAB|CLINIC|EHR|MAIN|202501181230||ORU^R01|NOISY03|P|2.5
PID|1||99903^^^MRN||GRAMMAR^BAD||19601010|M
OBR|1|||LAB_NOTE
OBX|1|TX|RES^Result Note||GLUCOSE IS very HIGH 450!!! pt forgot to take insulin last nite... feels dizy and thirsty for 2 days suggests dka maybe?? ketone test ordered||||F"""
    },
    {
        "name": "Ambiguous Abbreviations",
        "description": "Heavy use of medical abbreviations (SOB, DOE, CHF).",
        "hl7": """MSH|^~\\&|CARDIOLOGY|HOSP|EHR|MAIN|202501181245||ORU^R01|NOISY04|P|2.5
PID|1||99904^^^MRN||ABBREV^HEAVY||19500101|F
OBR|1|||CARDIO_NOTE
OBX|1|TX|NOTE^Progress Note||Pt w/ h/o CHF p/w worsening DOE and PND. +3 pitting edema b/l. JVD present. Lungs w/ crackles @ bases. Plan: Lasix INC and monitor K+.||||F"""
    }
]

def run_tests():
    print("\n" + "=" * 70)
    print("NOISY DATA & HUMAN ERROR TEST")
    print("=" * 70)
    print("Testing resilience against typos, slang, and unstructured text.")
    print("Note: 6s delay between requests.\n")
    
    results = []
    
    for i, test in enumerate(TEST_MESSAGES, 1):
        if i > 1:
            print(f"Waiting 6s for rate limit...")
            time.sleep(6)
            
        print(f"[{i}/{len(TEST_MESSAGES)}] Sending: {test['name']}")
        print(f"   Context: {test['description']}")
        print(f"   Input Snippet: {test['hl7'].split('OBX|1|TX|')[1].split('||')[1][:60]}...")
        
        try:
            resp = requests.post(
                PARSE_ENDPOINT, 
                json={"hl7_text": test['hl7'], "use_llm": True, "persist": True}
            )
            resp.raise_for_status()
            data = resp.json()
            
            summary = data.get('clinical_summary', 'No summary generated')
            print(f"\n   ✅ Success! Agent Interpretation:")
            print(f"   \"{summary}\"\n")
            
            # Smart checks for understanding
            passed = True
            
            # Check 1: Typos (prain -> pain, elphant -> elephant/MI)
            if "Typo" in test['name']:
                if not any(x in summary.lower() for x in ['chest pain', 'angina', 'myocardial', 'heart attack']):
                    print("   ❌ Failed to identify chest pain from 'prain'")
                    passed = False
            
            # Check 2: Slang (tachy -> tachycardia, satting -> saturation)
            if "Slang" in test['name']:
                if not any(x in summary.lower() for x in ['tachycard', 'heart rate', 'hypox', 'oxygen']):
                    print("   ❌ Failed to interpret 'tachy' or 'satting'")
                    passed = False

            # Check 3: Grammar (High glucose 450)
            if "Grammar" in test['name']:
                if not any(x in summary.lower() for x in ['hyperglyc', 'glucose', 'insulin', 'dka', '450']):
                    print("   ❌ Failed to catch high glucose context")
                    passed = False

            # Check 4: Abbreviations (CHF, DOE, Edema)
            if "Abbrev" in test['name']:
                if not any(x in summary.lower() for x in ['heart failure', 'fluid', 'edema', 'breathing', 'dyspnea']):
                    print("   ❌ Failed to expand CHF/DOE abbreviations")
                    passed = False
            
            results.append({"name": test['name'], "status": "PASS" if passed else "FAIL"})
            
        except Exception as e:
            print(f"   ❌ Network/System Error: {e}")
            results.append({"name": test['name'], "status": "ERROR"})
            
    print("\n" + "=" * 70)
    print("TEST REPORT")
    print("=" * 70)
    for r in results:
        icon = "✅" if r['status'] == "PASS" else "❌"
        print(f"{icon} {r['name']}")

if __name__ == "__main__":
    run_tests()
