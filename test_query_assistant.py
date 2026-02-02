
import os
import sys
import json
from app.query_assistant import process_query

# Ensure we have DB access
os.environ["DATABASE_PATH"] = "agent.db"

def test_queries():
    print("Testing AI Query Assistant with Context...")
    
    # 1. Ask about a specific patient
    q1 = "What is David Danger's Troponin level?"
    print(f"\nQUERY 1: {q1}")
    r1 = process_query(q1)
    if r1["success"]:
        print(f"ANSWER 1: {r1['answer']}")
        
        # 2. Ask a follow-up (contextual)
        q2 = "Does he have any other alerts?"
        # Simulate history passing
        history = [
            {"role": "user", "content": q1},
            {"role": "ai", "content": r1["answer"]}
        ]
        
        print(f"\nQUERY 2 (Follow-up): {q2}")
        print(f"CTX: {[m['content'] for m in history]}")
        
        r2 = process_query(q2, history)
        if r2["success"]:
            print(f"SUCCESS")
            print(f"SQL: {r2['sql_used']}")
            print(f"ANSWER 2: {r2['answer']}")
        else:
            print(f"FAILED: {r2['error']}")
    else:
        print(f"FAILED Q1: {r1['error']}")

if __name__ == "__main__":
    test_queries()
