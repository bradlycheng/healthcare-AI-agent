import requests
import time
import json

BASE_URL = "http://localhost:8080"

def test_mode(mode, question):
    print(f"\n--- Testing Mode: {mode.upper()} ---")
    start = time.time()
    payload = {
        "question": question,
        "history": [],
        "reasoning_depth": mode
    }
    try:
        response = requests.post(f"{BASE_URL}/api/query", json=payload, timeout=60)
        duration = time.time() - start
        
        if response.status_code != 200:
            print(f"FAILED: {response.status_code} - {response.text}")
            return
            
        data = response.json()
        print(f"Status: {data.get('success')}")
        print(f"Latency: {duration:.2f}s")
        print(f"Answer: {data.get('answer', '')[:100]}...")
        
        trace = data.get('reasoning_trace', [])
        if not trace: 
             print("Trace: []")
        else:
            print(f"Trace Steps: {len(trace)}")
            for i, step in enumerate(trace):
                thought = step.get('thought', '')
                print(f"  Step {i+1}: {thought[:80]}...")
            
        if mode == 'deep':
            # Check for reflection
            # In our implementation, reflection is a step with thought starting with "Deep Mode Reflection"
            has_reflection = any("Deep Mode Reflection" in str(s.get('thought', '')) for s in trace)
            print(f"Has Reflection Step: {has_reflection}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Starting Deep Mode Verification...")
    
    # 1. Fast Mode - Expect low latency, 1 step (fake trace)
    test_mode("fast", "Show all patients")
    
    # 2. Standard Mode - Expect moderate latency, multiple steps
    test_mode("standard", "Who has the highest glucose?")
    
    # 3. Deep Mode - Expect higher latency, reflection step
    test_mode("deep", "Analyze the risk factors for patient John Smith relative to guidelines.")
