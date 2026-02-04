
from app.query_assistant import process_query
import json
import sys

def test_queries():
    print("Testing AI Query Capabilities on New Data...\n")
    
    queries = [
        "Show me all patients with diabetes.",
        "Who is taking Metformin?",
        "Show me the visits for the patient taking Metformin.",
    ]
    
    # We will maintain a history object to simulate a conversation for the last query
    history = []
    
    for q in queries:
        print(f"User: {q}")
        print("-" * 40)
        
        result = process_query(q, history)
        
        if result['success']:
            print(f"SQL Generated: {result['sql_used']}")
            print(f"Row Count: \033[92m{result['row_count']}\033[0m") # Green for visibility
            print(f"AI Answer: {result['answer']}")
            
            # Update history for context
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": result['answer']})
        else:
            print(f"\033[91mFAILED: {result.get('error')}\033[0m")
            
        print("\n" + "=" * 60 + "\n")

if __name__ == "__main__":
    test_queries()
