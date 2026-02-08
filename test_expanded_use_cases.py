
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.healthcare_agent import HealthcareAgent

if __name__ == "__main__":
    agent = HealthcareAgent()
    
    queries = [
        "Show patients on Metformin",
        "List all visits for Dr. Alice Chen",
        "Find male patients over 60 with diabetes"
    ]
    
    for q in queries:
        print(f"\n--- Testing: '{q}' ---")
        try:
            result = agent.run(q)
            if result.success:
                print(f"Answer: {result.answer}")
                print("Reasoning Logic:")
                for step in result.reasoning_trace:
                     print(f"  Thought: {step.thought}")
                     for tc in step.tool_calls:
                         print(f"  Tool: {tc.tool} | Input: {tc.input}")
                         if tc.tool == "query_database":
                            # Check sql if available in result
                             for tr in step.tool_results:
                                 if isinstance(tr.result, dict) and "sql" in tr.result:
                                     print(f"  SQL: {tr.result['sql']}")
            else:
                print(f"FAILED: {result.error}")
        except Exception as e:
            print(f"ERROR: {e}")
