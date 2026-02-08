
import sys
import os
import io
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.healthcare_agent import HealthcareAgent

def run_query(agent, query):
    print(f"\n--- Query: '{query}' ---")
    try:
        result = agent.run(query)
        if result.success:
            print(f"Answer: {result.answer}")
            print("Reasoning Trace:")
            for step in result.reasoning_trace:
                print(f"  Thought: {step.thought}")
                for tc in step.tool_calls:
                    print(f"  Tool: {tc.tool} | Input: {tc.input}")
                    
            # Basic validation logic
            trace_str = str(result.reasoning_trace).lower()
            if "diabetes" in query.lower() and ("glucose" in trace_str or "a1c" in trace_str):
                 print("[PASS] Diabetes logic triggered")
            elif "hypertension" in query.lower() and ("bp" in trace_str or "pressure" in trace_str):
                 print("[PASS] Hypertension logic triggered")
            elif "kidney" in query.lower() and ("creatinine" in trace_str or "egfr" in trace_str):
                 print("[PASS] Renal logic triggered")
            else:
                 print("[WARN] Specific logic might be missing")
                 
        else:
            print(f"FAILED: {result.error}")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    agent = HealthcareAgent()
    
    # 1. Diabetes
    run_query(agent, "How are my diabetic patients doing?")
    
    # 2. Hypertension
    run_query(agent, "Show me patients with hypertension problems")
    
    # 3. Renal
    run_query(agent, "List patients with kidney issues")
