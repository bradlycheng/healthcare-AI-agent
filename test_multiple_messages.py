"""
Test Multiple HL7 Messages and Analyze Results
================================================
This script sends various HL7 messages to the Healthcare AI Agent API
and analyzes the results to validate processing quality.
"""

import sys
import io

# Fix Windows console encoding for Unicode
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json
from datetime import datetime
from typing import Dict, Any, List

API_BASE = "http://localhost:8080"
PARSE_ENDPOINT = f"{API_BASE}/oru/parse"

# Test Messages - Various clinical scenarios
TEST_MESSAGES = [
    {
        "name": "Basic Glucose Test",
        "description": "Simple high glucose result",
        "hl7": """MSH|^~\\&|HIS|MedCenter|LIS|LocalLab|202405021000||ORU^R01|MSG1001|P|2.3
PID|1||123456^^^MRN||DOE^JOHN||19800101|M
OBR|1|||BASIC_PANEL
OBX|1|NM|GLU^Glucose||105|mg/dL|70-100|H|||F"""
    },
    {
        "name": "Complete Blood Panel",
        "description": "Multiple lab results with high and low flags",
        "hl7": """MSH|^~\\&|LAB|HOSPITAL|EHR|CLINIC|202501170900||ORU^R01|MSG2001|P|2.5
PID|1||987654^^^MRN||SMITH^JANE||19751215|F
OBR|1|||CBC_PANEL
OBX|1|NM|WBC^White Blood Count||12.5|x10^9/L|4.5-11.0|H|||F
OBX|2|NM|RBC^Red Blood Count||4.2|x10^12/L|4.0-5.5|N|||F
OBX|3|NM|HGB^Hemoglobin||11.8|g/dL|12.0-16.0|L|||F
OBX|4|NM|PLT^Platelets||250|x10^9/L|150-400|N|||F"""
    },
    {
        "name": "Blood Pressure Measurement",
        "description": "Vital signs with blood pressure components",
        "hl7": """MSH|^~\\&|VITALS|ICU|EHR|MAIN|202501171030||ORU^R01|MSG3001|P|2.5
PID|1||555111^^^MRN||JOHNSON^ROBERT||19600520|M
OBR|1|||VITAL_SIGNS
OBX|1|NM|SBP^Systolic Blood Pressure||145|mmHg|90-120|H|||F
OBX|2|NM|DBP^Diastolic Blood Pressure||92|mmHg|60-80|H|||F
OBX|3|NM|HR^Heart Rate||88|bpm|60-100|N|||F
OBX|4|NM|TEMP^Temperature||98.6|F|97.0-99.0|N|||F"""
    },
    {
        "name": "Lipid Panel",
        "description": "Cholesterol and lipid results",
        "hl7": """MSH|^~\\&|LAB|CARDIO|EHR|CLINIC|202501171100||ORU^R01|MSG4001|P|2.5
PID|1||789012^^^MRN||WILLIAMS^MARY||19850310|F
OBR|1|||LIPID_PANEL
OBX|1|NM|CHOL^Total Cholesterol||220|mg/dL|<200|H|||F
OBX|2|NM|HDL^HDL Cholesterol||55|mg/dL|>40|N|||F
OBX|3|NM|LDL^LDL Cholesterol||140|mg/dL|<100|H|||F
OBX|4|NM|TRIG^Triglycerides||175|mg/dL|<150|H|||F"""
    },
    {
        "name": "Numeric Only Message",
        "description": "Message with only numeric data (should skip LLM per conditional logic)",
        "hl7": """MSH|^~\\&|LAB|MAIN|EHR|MAIN|202501171200||ORU^R01|MSG5001|P|2.5
PID|1||111222^^^MRN||BROWN^DAVID||19900415|M
OBR|1|||CHEM7
OBX|1|NM|NA^Sodium||140|mEq/L|136-145|N|||F
OBX|2|NM|K^Potassium||4.2|mEq/L|3.5-5.0|N|||F
OBX|3|NM|CL^Chloride||102|mEq/L|98-106|N|||F"""
    },
    {
        "name": "Text Observations with Clinical Notes",
        "description": "Message with text content that should invoke LLM",
        "hl7": """MSH|^~\\&|LAB|RADIOLOGY|EHR|MAIN|202501171300||ORU^R01|MSG6001|P|2.5
PID|1||333444^^^MRN||GARCIA^MARIA||19780822|F
OBR|1|||XRAY_CHEST
OBX|1|TX|XRAY^Chest X-Ray Interpretation||Mild cardiomegaly noted. No acute infiltrates. Small left pleural effusion. Recommend follow-up imaging in 2 weeks.||||F
OBX|2|NM|HEART_SIZE^Heart Size||14.5|cm|<13|H|||F"""
    },
]


def send_message(hl7_text: str, use_llm: bool = True, persist: bool = False) -> Dict[str, Any]:
    """Send an HL7 message to the API and return the response."""
    payload = {
        "hl7_text": hl7_text,
        "use_llm": use_llm,
        "persist": persist
    }
    
    try:
        response = requests.post(PARSE_ENDPOINT, json=payload, timeout=60)
        response.raise_for_status()
        return {
            "success": True,
            "status_code": response.status_code,
            "data": response.json(),
            "elapsed_time": response.elapsed.total_seconds()
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "response_text": getattr(e.response, 'text', None) if hasattr(e, 'response') else None
        }


def analyze_response(result: Dict[str, Any], test_name: str) -> Dict[str, Any]:
    """Analyze the API response for quality and correctness."""
    analysis = {
        "test_name": test_name,
        "success": result.get("success", False),
        "elapsed_time": result.get("elapsed_time", 0)
    }
    
    if not result.get("success"):
        analysis["error"] = result.get("error")
        return analysis
    
    data = result.get("data", {})
    
    # Patient Analysis
    patient = data.get("patient", {})
    analysis["patient"] = {
        "id": patient.get("id", "N/A"),
        "name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip(),
        "dob": patient.get("dob", "N/A"),
        "sex": patient.get("sex", "N/A")
    }
    
    # Clinical Summary Analysis
    clinical_summary = data.get("clinical_summary", "")
    analysis["clinical_summary"] = {
        "content": clinical_summary[:200] + "..." if len(clinical_summary) > 200 else clinical_summary,
        "length": len(clinical_summary),
        "has_content": len(clinical_summary) > 10
    }
    
    # Observations Analysis
    observations = data.get("structured_observations", [])
    analysis["observations"] = {
        "count": len(observations),
        "items": []
    }
    
    for obs in observations:
        obs_item = {
            "code": obs.get("code", "N/A"),
            "display": obs.get("display", "N/A"),
            "value": obs.get("value", "N/A"),
            "unit": obs.get("unit", "N/A"),
            "flag": obs.get("flag", "")
        }
        analysis["observations"]["items"].append(obs_item)
    
    # FHIR Bundle Analysis
    fhir_bundle = data.get("fhir_bundle", {})
    entries = fhir_bundle.get("entry", [])
    analysis["fhir_bundle"] = {
        "resource_type": fhir_bundle.get("resourceType", "N/A"),
        "bundle_type": fhir_bundle.get("type", "N/A"),
        "entry_count": len(entries),
        "resources": [entry.get("resource", {}).get("resourceType", "Unknown") for entry in entries]
    }
    
    return analysis


def print_analysis(analysis: Dict[str, Any]):
    """Pretty print the analysis results."""
    print("\n" + "=" * 70)
    print(f"TEST: {analysis['test_name']}")
    print("=" * 70)
    
    if not analysis.get("success"):
        print(f"❌ FAILED: {analysis.get('error')}")
        return
    
    print(f"✅ SUCCESS (Response Time: {analysis['elapsed_time']:.2f}s)")
    
    # Patient Info
    patient = analysis.get("patient", {})
    print(f"\n📋 PATIENT:")
    print(f"   ID: {patient.get('id')}")
    print(f"   Name: {patient.get('name')}")
    print(f"   DOB: {patient.get('dob')}")
    print(f"   Sex: {patient.get('sex')}")
    
    # Clinical Summary
    summary = analysis.get("clinical_summary", {})
    print(f"\n📝 CLINICAL SUMMARY:")
    print(f"   Length: {summary.get('length')} chars")
    print(f"   Content: {summary.get('content')}")
    
    # Observations
    obs = analysis.get("observations", {})
    print(f"\n🔬 OBSERVATIONS ({obs.get('count')} items):")
    for item in obs.get("items", []):
        flag_emoji = "⬆️" if item['flag'] == 'H' else ("⬇️" if item['flag'] == 'L' else "✔️")
        print(f"   {flag_emoji} {item['display']}: {item['value']} {item['unit']} [{item['flag'] or 'N'}]")
    
    # FHIR Bundle
    fhir = analysis.get("fhir_bundle", {})
    print(f"\n🏥 FHIR BUNDLE:")
    print(f"   Type: {fhir.get('bundle_type')}")
    print(f"   Entries: {fhir.get('entry_count')}")
    print(f"   Resources: {', '.join(fhir.get('resources', []))}")


def run_all_tests():
    """Run all test cases and collect results."""
    import time
    
    # Rate limit is 5 seconds between LLM requests
    RATE_LIMIT_DELAY = 6  # seconds
    
    print("\n" + "=" * 70)
    print("HEALTHCARE AI AGENT - MULTIPLE MESSAGE TEST")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Note: {RATE_LIMIT_DELAY}s delay between requests for rate limiting")
    print("=" * 70)
    
    results = []
    
    for i, test in enumerate(TEST_MESSAGES, 1):
        # Wait between requests to respect rate limit (skip first request)
        if i > 1:
            print(f"\n   Waiting {RATE_LIMIT_DELAY}s for rate limit...")
            time.sleep(RATE_LIMIT_DELAY)
        
        print(f"\n[{i}/{len(TEST_MESSAGES)}] Sending: {test['name']}...")
        print(f"   Description: {test['description']}")
        
        # Send the message
        result = send_message(test['hl7'], use_llm=True, persist=False)
        
        # Analyze the response
        analysis = analyze_response(result, test['name'])
        results.append(analysis)
        
        # Print individual analysis
        print_analysis(analysis)
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    successful = sum(1 for r in results if r.get("success"))
    failed = len(results) - successful
    total_time = sum(r.get("elapsed_time", 0) for r in results)
    avg_time = total_time / len(results) if results else 0
    
    print(f"\n✅ Successful: {successful}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")
    print(f"⏱️  Total Time: {total_time:.2f}s")
    print(f"⏱️  Average Time: {avg_time:.2f}s per message")
    
    # Observation Statistics
    total_obs = sum(r.get("observations", {}).get("count", 0) for r in results if r.get("success"))
    print(f"\n🔬 Total Observations Processed: {total_obs}")
    
    # FHIR Resource Statistics
    all_resources = []
    for r in results:
        if r.get("success"):
            all_resources.extend(r.get("fhir_bundle", {}).get("resources", []))
    
    resource_counts = {}
    for res in all_resources:
        resource_counts[res] = resource_counts.get(res, 0) + 1
    
    print(f"\n🏥 FHIR Resources Generated:")
    for res_type, count in sorted(resource_counts.items()):
        print(f"   {res_type}: {count}")
    
    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70 + "\n")
    
    return results


if __name__ == "__main__":
    run_all_tests()
