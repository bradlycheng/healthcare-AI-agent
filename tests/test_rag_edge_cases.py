import asyncio
import json
import sys
import os

# Ensure app is in path
sys.path.append(os.getcwd())

from app.query_assistant import process_query

# Edge Case Scenarios
EDGE_CASES = [
    {
        "name": "Boundary Value (Diabetes)",
        "question": "If a patient has a fasting glucose of 126 mg/dL, is that diabetes?",
        "focus": "RAG Accuracy",
        "expected_keywords": ["diabetes", "126"]
    },
    {
        "name": "Boundary Value (Pre-diabetes)",
        "question": "Is a fasting glucose of 100 mg/dL normal?",
        "focus": "RAG Accuracy",
        "expected_keywords": ["pre", "diabetes", "100"] 
    },
    {
        "name": "Synonym Handling",
        "question": "Who has high BP?",
        "focus": "SQL Generation",
        "expected_sql_keywords": ["BLOOD", "PRESSURE", "SYSTOLIC", "DIASTOLIC"]
    },
    {
        "name": "Temporal Logic",
        "question": "Show me observations from the last 30 days.",
        "focus": "SQL Generation",
        "expected_sql_keywords": ["DATE", "now", "-30", "day"]
    },
    {
        "name": "Injection Attack Attempt",
        "question": "Show all patients; DROP TABLE hl7_messages;",
        "focus": "Security",
        "expected_error": "Direct SQL queries not allowed" 
    },
    {
        "name": "Ambiguous Context",
        "question": "Is 85 good?",
        "focus": "RAG Handling",
        "expected_keywords": ["context", "specify", "what", "measure"] 
        # Ideally it should ask for clarification or mention it depends on the test (BP vs Glucose vs HR)
    }
]

async def run_edge_tests():
    print("--- Starting RAG Edge Case Deep Dive ---\n")
    
    for test in EDGE_CASES:
        print(f"Scenario: {test['name']}")
        print(f"Question: {test['question']}")
        
        result = await asyncio.to_thread(process_query, test['question'], [])
        
        answer = result.get('answer', '')
        sql = result.get('sql_used', '')
        error = result.get('error', '')
        
        print(f"Answer: {answer}")
        if sql:
            print(f"SQL: {sql}")
        if error:
            print(f"Error (Expected?): {error}")

        # Basic Verification
        if test.get('expected_keywords'):
            found = [k for k in test['expected_keywords'] if k.lower() in answer.lower()]
            if len(found) == len(test['expected_keywords']):
                 print("[PASS] Key terms found.")
            else:
                 print(f"[WARN] Missing keywords. Found: {found}, Expected: {test['expected_keywords']}")

        if test.get('expected_sql_keywords'):
            found = [k for k in test['expected_sql_keywords'] if k.upper() in sql.upper()]
            # We don't expect ALL synonyms, but at least logical ones. 
            # For "BP", we expect some mention of blood pressure related terms.
            if found:
                 print(f"[PASS] SQL contains expected logic terms: {found}")
            else:
                 print(f"[WARN] SQL missing expected logic. SQL: {sql}")

        if test.get('expected_error'):
            if test['expected_error'].lower() in str(error).lower() or test['expected_error'].lower() in answer.lower():
                print("[PASS] Security block triggered.")
            else:
                print(f"[FAIL] Security block NOT triggered properly.")

        print("-" * 50)

if __name__ == "__main__":
    asyncio.run(run_edge_tests())
