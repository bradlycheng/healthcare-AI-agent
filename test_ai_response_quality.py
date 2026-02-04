
from app.query_assistant import process_query
import json

def test_comprehensive():
    print("=" * 70)
    print("COMPREHENSIVE AI RESPONSE QUALITY TEST")
    print("=" * 70 + "\n")
    
    test_cases = [
        # Basic counts
        ("How many patients do we have?", []),
        
        # Specific patient lookup
        ("Show me John Williams' lab results", []),
        
        # Pronoun follow-up (context test)
        ("What medications is he taking?", [
            {"role": "user", "content": "Show me John Williams' lab results"},
            {"role": "assistant", "content": "John Williams has the following results..."}
        ]),
        
        # Aggregation
        ("Who has the highest glucose level?", []),
        
        # Negative query
        ("Which patients have NO abnormal results?", []),
        
        # Clinical interpretation (should use RAG)
        ("Is a glucose of 180 mg/dL dangerous?", []),
        
        # Multi-condition
        ("Show patients with both diabetes AND hypertension", []),
        
        # Empty result expected
        ("Show all patients named Zzzzzz", []),
    ]
    
    passed = 0
    failed = 0
    
    for question, history in test_cases:
        print(f"Q: {question}")
        if history:
            print(f"   [With history context]")
        print("-" * 50)
        
        result = process_query(question, history)
        
        if result['success']:
            print(f"Rows: {result['row_count']}")
            print(f"AI:   {result['answer'][:200]}..." if len(result['answer']) > 200 else f"AI:   {result['answer']}")
            
            # Basic sanity checks
            issues = []
            
            # Check for hallucination - says found data but no results
            if result['row_count'] == 0 and "found" in result['answer'].lower():
                if "no" not in result['answer'].lower() and "0" not in result['answer'][:50]:
                    issues.append("May be hallucinating results")
                
            if result['row_count'] == 0 and ("found" in result['answer'].lower() and "patients" in result['answer'].lower()):
                if "no" not in result['answer'].lower() and "0" not in result['answer']:
                    issues.append("May be hallucinating results")
            
            if issues:
                print(f"   WARNINGS: {issues}")
                failed += 1
            else:
                print(f"   OK")
                passed += 1
        else:
            print(f"FAILED: {result.get('error')}")
            failed += 1
            
        print("\n")
    
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)}")
    print("=" * 70)

if __name__ == "__main__":
    test_comprehensive()
