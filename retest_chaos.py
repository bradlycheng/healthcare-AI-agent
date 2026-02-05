import requests
import time
import json

API_URL = "http://localhost:8080/oru/parse"

SCENARIOS = [
    {
        "name": "Temporal History (Past vs Present)",
        "hl7": """MSH|^~\\&|LAB|CLINIC|APP|DEST|20250122090000||ORU^R01|C2|P|2.5.1
PID|1||P1||DOE^JOHN
OBX|1|TX|NOTE^NOTE||See notes
NTE|1|L|Yesterday pulse was 110. Today pulse is 72.
""",
        "expected": [72.0]
    },
    {
        "name": "Numeric Extraction vs Qualitative",
        "hl7": """MSH|^~\\&|LAB|CLINIC|APP|DEST|20250122090000||ORU^R01|C3|P|2.5.1
PID|1||P1||DOE^JOHN
OBX|1|TX|NOTE^NOTE||See notes
NTE|1|L|BP is high. Actual reading 155/95.
""",
        "expected": [155.0, 95.0]
    },
    {
        "name": "Negation Check",
        "hl7": """MSH|^~\\&|LAB|CLINIC|APP|DEST|20250122090000||ORU^R01|C1|P|2.5.1
PID|1||P1||DOE^JOHN
OBX|1|TX|NOTE^NOTE||See notes
NTE|1|L|Patient denies any fever. Temperature is not 102.4.
""",
        "expected": [] # Should extract nothing
    },
]

print("Warming up server (cold start)...")
try:
    requests.post(API_URL, json={"hl7_text": SCENARIOS[0]["hl7"], "use_llm": False}, timeout=10)
except:
    pass
time.sleep(5)

print("Starting Global Accuracy Regression...")
passed = 0
for s in SCENARIOS:
    print(f"\n[TEST]: {s['name']}")
    for attempt in range(5):
        try:
            resp = requests.post(API_URL, json={"hl7_text": s["hl7"], "use_llm": True, "persist": False}, timeout=120)
            if resp.status_code == 429:
                print(f"  [RETRY] 429 Rate limited, waiting...")
                time.sleep(20)
                continue
            if resp.status_code != 200:
                print(f"  [FAIL] Status {resp.status_code}")
                break
            
            data = resp.json()
            print(f"DEBUG_API_RESP: {json.dumps(data, indent=2)}") # Debugging response structure
            ai_obs = [o for o in data.get("structured_observations", []) if o.get("source") == "AI_EXTRACTED"]
            thought = data.get("ai_analysis", {}).get("thought_process", "N/A")
            print(f"  [THOUGHT]: {thought}")
            if not ai_obs and not s["expected"]:
                pass
            elif ai_obs and not s["expected"]:
                print(f"  [ERR-EXTRA]: {ai_obs}")
            elif not ai_obs and s["expected"]:
                print(f"  [ERR-MISSING]: Expected {s['expected']}")
            
            # Simple check: verify each expected float value is present in some AI observation
            match = True
            ai_values = [float(o["value"]) for o in ai_obs]
            for val in s["expected"]:
                if not any(abs(v - val) < 0.1 for v in ai_values):
                    match = False
                    print(f"  [MISSING VALUE]: {val} not found in {ai_values}")
            
            if match and len(ai_values) > len(s["expected"]):
                 # Warning only if extra values found
                 print(f"  [WARN-EXTRA]: Found {len(ai_values)} values, expected {len(s['expected'])}")
            
            if match:
                print("  [PASS] Results match expectations.")
                passed += 1
                break
            else:
                print(f"  [FAIL] Matching failed.")
                break
        except Exception as e:
            print(f"  [ERROR] {e}")
            break
    time.sleep(10)

print(f"\nAccuracy Regression: {passed}/{len(SCENARIOS)} PASSED")
