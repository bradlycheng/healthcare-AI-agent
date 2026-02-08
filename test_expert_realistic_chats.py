import requests
import json
import time

import sys
import io

# Fix for Windows terminal encoding issues
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

API_URL = "http://localhost:8080/api/query"

def run_query(question, history=None, depth="standard"):
    payload = {
        "question": question,
        "history": history or [],
        "reasoning_depth": depth
    }
    start_time = time.time()
    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        latency = time.time() - start_time
        if response.status_code == 200:
            return response.json(), latency
        else:
            print(f"Error: {response.status_code} - {response.text}")
            return None, latency
    except Exception as e:
        print(f"Connection failed: {e}")
        return None, 0

def log_test(scenario, question, response, latency):
    print(f"\n--- {scenario} ---")
    print(f"Question: {question}")
    if response:
        print(f"Latency: {latency:.2f}s")
        print(f"Answer: {response.get('answer')}")
        trace = response.get("reasoning_trace", [])
        print(f"Trace Steps: {len(trace)}")
        for i, step in enumerate(trace):
            print(f"  Step {i+1}: {step.get('thought')[:100]}...")
    else:
        print("FAILED to get response")

def test_scenario_1():
    """Multi-turn Contextual Follow-up."""
    print("\nStarting Scenario 1: Multi-turn Contextual Follow-up")
    
    # Step 1: Baseline lookup
    q1 = "What is the latest glucose for John Smith?"
    res1, lat1 = run_query(q1, depth="fast")
    log_test("Scenario 1, Step 1 (FAST)", q1, res1, lat1)
    
    # Step 2: Contextual follow-up
    history = [{"role": "user", "content": q1}, {"role": "assistant", "content": res1.get("answer", "")}]
    q2 = "Is that value considered high according to the diabetes guidelines?"
    res2, lat2 = run_query(q2, history=history, depth="deep")
    log_test("Scenario 1, Step 2 (DEEP)", q2, res2, lat2)

def test_scenario_2():
    """Multi-Patient Comparison."""
    print("\nStarting Scenario 2: Multi-Patient Comparison")
    q = "Compare the latest blood pressure readings for John Smith and Sarah Jenkins."
    res, lat = run_query(q, depth="standard")
    log_test("Scenario 2 (STANDARD)", q, res, lat)

def test_scenario_3():
    """Clinical Trend + Guideline Synthesis."""
    print("\nStarting Scenario 3: Clinical Trend + Guideline Synthesis")
    q = "Analyze Sarah Jenkins' blood pressure over the last 3 recordings. Does she meet the criteria for Hypertension Stage 2?"
    res, lat = run_query(q, depth="deep")
    log_test("Scenario 3 (DEEP)", q, res, lat)

def test_scenario_4():
    """Cross-table Join (Operational + Clinical)."""
    print("\nStarting Scenario 4: Cross-table Join")
    q = "Show me all providers who have treated patients with HbA1c > 8 this month."
    res, lat = run_query(q, depth="standard")
    log_test("Scenario 4 (STANDARD)", q, res, lat)

def test_scenario_5():
    """Mixed Subjective Reasoning."""
    print("\nStarting Scenario 5: Mixed Subjective Reasoning")
    q = "Based on the database records, which patient seems to be at the highest risk for cardiovascular complications?"
    res, lat = run_query(q, depth="deep")
    log_test("Scenario 5 (DEEP)", q, res, lat)

if __name__ == "__main__":
    print("Beginning Expert Realistic Chat Testing...")
    test_scenario_1()
    test_scenario_2()
    test_scenario_3()
    test_scenario_4()
    # test_scenario_5() # This might be slow/complex, keep it optional
    print("\nExpert Testing Complete.")
