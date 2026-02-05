import asyncio
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.query_assistant import process_query

# Mock History: The user previously asked about John Smith's Glucose
MOCK_HISTORY = [
    {"role": "user", "content": "What is John Smith's glucose level?"},
    {"role": "assistant", "content": "John Smith's glucose is 85 mg/dL."}
]

async def test_context_memory():
    print("--- Testing Context Memory vs Ambiguity ---")
    
    # This query IS ambiguous in isolation, but NOT ambiguous given history
    question = "Is that normal?" 
    print(f"History Context: {MOCK_HISTORY[-1]['content']}")
    print(f"Question: {question}")
    
    result = await asyncio.to_thread(process_query, question, MOCK_HISTORY)
    
    answer = result.get('answer', '')
    sql = result.get('sql_used', '')
    
    print(f"Answer: {answer}")
    print(f"SQL: {sql}")
    
    if "specify" in answer.lower():
        print("[FAIL] System blocked valid context-aware query.")
    elif "glucose" in sql.lower() or "85" in answer:
        print("[PASS] System correctly used history to resolve ambiguity.")
    else:
        print("[WARN] Unknown behavior.")

if __name__ == "__main__":
    asyncio.run(test_context_memory())
