
import requests
import json
import time

URL = "http://localhost:8080/api/query"

def test_conversation(name, queries):
    """
    Test a conversation chain.
    queries = [(question, expected_keywords, description), ...]
    """
    print(f"\n{'='*80}")
    print(f"{name}")
    print('='*80)
    
    history = []
    passed = 0
    failed = 0
    
    for i, (question, expected, desc) in enumerate(queries, 1):
        print(f"\nQ{i}: {question}")
        print(f"    {desc}")
        
        try:
            # Longer delay to avoid rate limits
            if i > 1:
                time.sleep(7)
            
            resp = requests.post(URL, json={"question": question, "history": history})
            
            if resp.status_code == 429:
                print("    [SKIP] Rate limited")
                continue
            
            data = resp.json()
            success = data.get('success', False)
            answer = data.get('answer', '')
            sql = data.get('sql_used', '')
            
            # Check for expected context
            context_ok = True
            missing = []
            if expected:
                for keyword in expected:
                    if keyword.upper() not in sql.upper():
                        context_ok = False
                        missing.append(keyword)
            
            if context_ok or not expected:
                print(f"    [OK] Context retained")
                if expected:
                    print(f"         Found: {', '.join(expected)}")
                passed += 1
            else:
                print(f"    [X] Missing context: {', '.join(missing)}")
                print(f"        SQL: {sql[:100]}")
                failed += 1
            
            # Add to history
            history.append({"role": "user", "content": question})
            history.append({"role": "ai", "content": answer})
            
        except Exception as e:
            print(f"    [ERROR] {e}")
            failed += 1
    
    return passed, failed

def main():
    print("="*80)
    print("CONVERSATIONAL MEMORY TESTS (SLOW - NO RATE LIMITS)")
    print("="*80)
    
    total_passed = 0
    total_failed = 0
    
    # Test 1: Basic pronoun resolution
    p, f = test_conversation(
        "TEST 1: Pronoun Resolution (he/she/his/her)",
        [
            ("Show me John Smith's results", [], "Establish subject: John Smith"),
            ("What's his glucose level?", ["JOHN", "SMITH", "GLUCOSE"], "'his' = John Smith"),
            ("Does he have abnormal values?", ["JOHN", "SMITH"], "'he' = John Smith"),
        ]
    )
    total_passed += p
    total_failed += f
    
    # Test 2: Context switching
    p, f = test_conversation(
        "TEST 2: Context Switching Between Patients",
        [
            ("Show Barbara Gordon's vitals", ["BARBARA", "GORDON"], "Patient 1: Barbara"),
            ("What about Robert Chen?", ["ROBERT", "CHEN"], "Switch to Patient 2: Robert"),
            ("What's his cholesterol?", ["ROBERT", "CHEN", "CHOLESTEROL"], "'his' = most recent (Robert)"),
        ]
    )
    total_passed += p
    total_failed += f
    
    # Test 3: Narrowing down (them/they/their)
    p, f = test_conversation(
        "TEST 3: Narrowing Down Results (them/their)",
        [
            ("Show all patients with abnormal results", [], "Broad search"),
            ("Which of them have high glucose?", ["GLUCOSE"], "'them' = patients with abnormal results"),
        ]
    )
    total_passed += p
    total_failed += f
    
    # Test 4: Implicit context (no pronoun)
    p, f = test_conversation(
        "TEST 4: Implicit Context (no explicit pronoun)",
        [
            ("Show Barbara Gordon's blood pressure", ["BARBARA", "GORDON", "BLOOD", "PRESSURE"], "Explicit patient"),
            ("What about heart rate?", ["BARBARA", "GORDON", "HEART"], "Implied: same patient"),
        ]
    )
    total_passed += p
    total_failed += f
    
    # Summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    total = total_passed + total_failed
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    
    if total > 0:
        success_rate = (total_passed / total) * 100
        print(f"Success Rate: {success_rate:.1f}%")
    
    if total_failed == 0 and total_passed > 0:
        print("\n[SUCCESS] All conversational memory tests passed!")
        print("Context retention is working correctly across:")
        print("  - Pronoun resolution (he/she/his/her)")
        print("  - Context switching between subjects")
        print("  - Referential expressions (them/their)")
        print("  - Implicit context continuation")
    elif total_failed > 0:
        print(f"\n[PARTIAL] {total_failed} context failures detected")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
