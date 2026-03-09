
import sys
import os
import json
import asyncio
from app.healthcare_agent import HealthcareAgent

async def debug_agent_ckd():
    agent = HealthcareAgent()
    print("QUERY: Show list of patients with eGFR < 60")
    # run_agent_query is a convenience function that initializes the agent
    from app.healthcare_agent import run_agent_query
    result = run_agent_query("Show list of patients with eGFR < 60", [])
    
    print(f"SUCCESS: {result.get('success')}")
    print(f"SQL USED: {result.get('sql_used')}")
    print(f"ROW COUNT: {result.get('row_count')}")
    print(f"ANSWER: {result.get('answer')}")
    print(f"TOOLS USED: {result.get('tools_used')}")
    
    if result.get("reasoning_trace"):
        print("\nREASONING TRACE:")
        for step in result["reasoning_trace"]:
            print(f"Thought: {step.get('thought')}")
            print(f"Tools: {step.get('tool_calls')}")

if __name__ == "__main__":
    asyncio.run(debug_agent_ckd())
