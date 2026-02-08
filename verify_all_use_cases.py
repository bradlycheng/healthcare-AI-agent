
import sys
import os
import time

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set DB Path BEFORE importing agent (or before init)
os.environ["DATABASE_PATH"] = "C:/Users/bradl/Desktop/healthcare_ai_agent/data/healthcare.db"

from app.healthcare_agent import HealthcareAgent

def run_test(name, query, history, expected_keywords, unexpected_keywords=[]):
    print(f"\n[{name}] Testing Query: '{query}'")
    agent = HealthcareAgent()
    start_time = time.time()
    response = agent.run(query, history)
    duration = time.time() - start_time
    
    print(f" -> Agent Answer: {response.answer}")
    print(f" -> SQL Used: {response.sql_used}")
    print(f" -> Latency: {duration:.2f}s")
    
    passed = True
    
    # Check expected keywords
    for kw in expected_keywords:
        if kw.lower() not in response.answer.lower() and kw.lower() not in str(response.sql_used).lower():
            print(f" [FAIL] Missing expected keyword: '{kw}'")
            passed = False
            
    # Check unexpected keywords
    for kw in unexpected_keywords:
        if kw.lower() in response.answer.lower() or kw.lower() in str(response.sql_used).lower():
            print(f" [FAIL] Found unexpected keyword: '{kw}'")
            passed = False
            
    if passed:
        print(" [PASS]")
    
    return response, passed

def verify_all_use_cases():
    print("=== Starting Comprehensive Use Case Verification ===\n")
    results = []

    # 1. Risk Stratification (The "Worried" Query)
    # Expecting: Sarah (BP), John (A1c/Glucose), specific high-risk vitals in SQL
    resp1, pass1 = run_test(
        "Risk Stratification",
        "Which patients should I be worried about?",
        [],
        ["Sarah", "John", "blood pressure", "glucose", "a1c"], # Expected patients/vitals
        []
    )
    results.append(("Risk Stratification", pass1))

    # 2. Chronic Disease - Hypertension (Sarah Jenkins)
    # Expecting: BP readings, Hypertension mention
    resp2, pass2 = run_test(
        "Hypertension (Sarah)",
        "Analyze blood pressure trends for Sarah Jenkins.",
        [],
        ["145", "150", "hypertension", "stage 2"], # Expected values/diagnosis
        []
    )
    results.append(("Hypertension", pass2))

    # 3. Context Switching (Sarah -> John -> Ambiguous)
    print("\n[Context Switching] Setup: User just asked about Sarah (History).")
    # Start fresh history for this flow
    history = []
    agent = HealthcareAgent() # Initialize agent here
    
    # Turn 1: Sarah
    q1 = "Analyze blood pressure trends for Sarah Jenkins."
    print(f"User: {q1}")
    resp1 = agent.run(q1, history)
    print(f"Agent: {resp1.answer}")
    history.append({"role": "user", "content": q1})
    history.append({"role": "assistant", "content": resp1.answer})
    
    # Turn 2: John (Switch)
    # Use a query that guarantees data retrieval so the specific context (Diabetes/BP) is established
    q2 = "What is John Smith's latest glucose?"
    resp3, pass3 = run_test(
        "Context Switch (John)",
        q2,
        history, # Should have Sarah in history
        ["John", "glucose"], 
        ["Sarah"] 
    )
    results.append(("Context Switch", pass3))
    
    # Add John to history
    history.append({"role": "user", "content": q2})
    history.append({"role": "assistant", "content": resp3.answer})
    
    # Turn 3: Ambiguous "Is it high?"
    # Should refer to John's Glucose
    q3 = "Is it high?"
    resp4, pass4 = run_test(
        "Ambiguous Follow-up ('Is it high?')",
        q3,
        history,
        ["high", "elevated", "yes", "no", "normal"], 
        ["Sarah"] 
    )
    
    print(f"DEBUG: History sent for 'Is it high?': {[m['content'] for m in history]}")
    
    if "glucose" in str(resp4.sql_used).lower() or "a1c" in str(resp4.sql_used).lower():
         print(" [PASS] Correctly inferred 'it' refers to John's Diabetes indicators.")
    elif "blood pressure" in str(resp4.sql_used).lower() and "glucose" not in str(resp4.sql_used).lower():
         print(" [WARN] Inferred BP for John. Acceptable if John has BP data.")
    else:
         print(f" [FAIL] Context unclear. SQL: {resp4.sql_used}")
    
    results.append(("Ambiguous Follow-up", pass4))

    print("\n=== Verification Summary ===")
    for name, passed in results:
        status = "PASSED" if passed else "FAILED"
        print(f"{name}: {status}")

if __name__ == "__main__":
    verify_all_use_cases()
