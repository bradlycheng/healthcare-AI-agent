import asyncio
import json
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.query_assistant import process_query

# Test Questions
TEST_CASES = [
    {
        "type": "NATURAL_SQL_COUNT",
        "question": "How many patients are in the database?",
        "expected_result": "count"
    },
    {
        "type": "NATURAL_SQL_FINDING",
        "question": "Show me all patients with Hypertension who are over 50 years old.",
        "expected_result": "patient list"
    },
    {
        "type": "RAG_KNOWLEDGE",
        "question": "What is the normal reference range for fasting glucose?",
        "expected_result": "70-100"
    },
    {
        "type": "RAG_CLINICAL_CONTEXT",
        "question": "Patient P123 has a glucose of 145 mg/dL. Is this concerning given the guidelines?",
        "expected_result": "high/diabetes"
    }
]

async def run_tests():
    print("--- Starting Deep RAG & Natural Query Test ---\n")
    
    for i, test in enumerate(TEST_CASES):
        print(f"Test {i+1}: [{test['type']}]")
        print(f"Question: {test['question']}")
        
        try:
             pass
        except:
            pass

        # Re-import to be safe
        from app.query_assistant import process_query
        
        # process_query signature: (question, history)
        # Returns dict: { 'answer': ..., 'sources': ..., ... }
        result = await asyncio.to_thread(process_query, test['question'], [])
        
        answer = result.get('answer', '')
        sources = result.get('sources', [])
        
        
        print(f"Answer: {answer}")
        
        if sources:
             print("Sources Used:")
             for s in sources:
                 snippet = s['snippet'].replace('\n', ' ')
                 print(f"   - {s['title']} ({s['relevance']}): {snippet[:100]}...")
        
        if test['expected_result'] in answer.lower():
             print("[PASS] RESULT: PASS (Keywords found)\n")
        else:
             print(f"[WARN] RESULT: VERIFY (Expected '{test['expected_result']}' not clear in answer)\n")
             
    print("--- Test Complete ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
