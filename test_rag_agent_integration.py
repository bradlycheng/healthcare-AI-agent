
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.healthcare_agent import HealthcareAgent

def run_rag_test():
    agent = HealthcareAgent()
    
    # Question requiring Data + Knowledge
    # "Is [Patient]'s blood pressure normal?"
    # Requires:
    # 1. query_database: Get BP for patient
    # 2. search_guidelines: Get BP guidelines (JNC 8)
    # 3. Synthesis: Compare value to guideline
    
    # We'll use a specific patient from the seed data
    # Let's pick "John Williams" or someone likely to exist (random seed)
    # Or better, we query for a hypertension patient first to get a name.
    
    print("--- Finding a patient with Hypertension ---")
    setup_q = "Show me a patient with high blood pressure"
    setup_res = agent.run(setup_q)
    if not setup_res.success or not setup_res.answer:
        print("Failed to find patient context.")
        return

    # Extract a name (naive approach, just take the first one mentioned or from results)
    # We can parse highlights or just ask the agent about "that patient"
    # But for a robust test, let's hardcode a known patient or use the setup result.
    
    patient_name = "John Williams" # High probability from seed, or we can use "P10000"
    
    query = f"According to JNC 8 guidelines, what stage of hypertension does {patient_name} have?"
    print(f"\n--- Testing RAG Integration: '{query}' ---")
    
    result = agent.run(query)
    
    print("\n--- AGENT RESPONSE ---")
    if result.success:
        print(f"Answer: {result.answer}")
        
        # Verification Steps
        print("\n--- VERIFICATION ---")
        
        # 1. Check for search_guidelines tool call
        has_rag_call = False
        for step in result.reasoning_trace:
            for tc in step.tool_calls:
                if tc.tool == "search_guidelines":
                    print(f"[PASS] Tool 'search_guidelines' called with input: {tc.input}")
                    has_rag_call = True
        
        if not has_rag_call:
            print("[FAIL] Agent did NOT call 'search_guidelines'. It might be hallucinating normalcy.")
            
        # 2. Check for Sources
        if result.sources:
            print(f"[PASS] Sources returned: {[s['title'] for s in result.sources]}")
        else:
            print("[WARN] No RAG sources attached to response.")
            
        # 3. Check synthesis logic
        lower_ans = result.answer.lower()
        if "normal" in lower_ans or "high" in lower_ans or "elevated" in lower_ans:
             print("[PASS] Agent provided a clinical assessment.")
        else:
             print("[WARN] Agent answer might be vague.")
             
    else:
        print(f"FAILED: {result.error}")

if __name__ == "__main__":
    run_rag_test()
