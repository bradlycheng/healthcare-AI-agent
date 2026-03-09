import sys
from app.healthcare_agent import HealthcareAgent
import json

# Force UTF-8 for stdout
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def test_agent():
    agent = HealthcareAgent()
    question = "Which patients I should be worried about"
    print(f"Question: {question}")
    
    response = agent.run(question)
    
    print(f"\nSuccess: {response.success}")
    print(f"Row count: {response.row_count}")
    print(f"SQL used: {response.sql_used}")
    print(f"\nAnswer:\n{response.answer}")
    print(f"\nHighlights: {response.highlights}")
    
    # Check trace
    for i, step in enumerate(response.reasoning_trace):
        print(f"\nStep {i+1} Thought: {step.thought}")
        for j, tr in enumerate(step.tool_results):
            print(f"  Tool {j+1} ({tr.tool}) result: {json.dumps(tr.result, indent=2)[:500]}...")

if __name__ == "__main__":
    test_agent()
