
import requests
import json
import time

URL = "http://localhost:8080/api/query"

class ConversationTest:
    """Helper class to manage conversation history."""
    
    def __init__(self, name):
        self.name = name
        self.history = []
        self.passed = 0
        self.failed = 0
        
    def ask(self, question, expected_context=None, description=""):
        """Ask a question and validate context retention."""
        print(f"\n  Q{len(self.history)//2 + 1}: {question}")
        if description:
            print(f"      {description}")
        
        try:
            resp = requests.post(URL, json={"question": question, "history": self.history})
            
            if resp.status_code == 429:
                print("      [SKIP] Rate limited")
                return None
            
            data = resp.json()
            success = data.get('success', False)
            answer = data.get('answer', '')
            sql = data.get('sql_used', '')
            row_count = data.get('row_count', 0)
            
            # Validate context if specified
            context_ok = True
            if expected_context:
                for keyword in expected_context:
                    if keyword.upper() not in sql.upper():
                        context_ok = False
                        print(f"      [X] Missing context: '{keyword}' not in SQL")
                        self.failed += 1
                        break
            
            if context_ok:
                print(f"      [OK] Success={success}, Rows={row_count}")
                if expected_context:
                    print(f"      [OK] Context retained: {', '.join(expected_context)}")
                self.passed += 1
            
            # Add to history
            self.history.append({"role": "user", "content": question})
            self.history.append({"role": "ai", "content": answer})
            
            time.sleep(2)  # Rate limit protection
            return data
            
        except Exception as e:
            print(f"      [ERROR] {e}")
            self.failed += 1
            return None
    
    def reset(self):
        """Reset conversation history."""
        self.history = []

def main():
    print("="*80)
    print("COMPREHENSIVE CONVERSATIONAL MEMORY TEST SUITE")
    print("="*80)
    
    all_passed = 0
    all_failed = 0
    
    # TEST 1: Basic pronoun resolution (he/she)
    print("\n" + "="*80)
    print("TEST 1: PRONOUN RESOLUTION - Patient Gender")
    print("="*80)
    
    t1 = ConversationTest("Pronoun Resolution")
    t1.ask("Show me John Smith's results", description="Initial query about John")
    t1.ask("What's his glucose level?", 
           expected_context=["JOHN", "SMITH", "GLUCOSE"],
           description="'his' should resolve to John Smith")
    t1.ask("Does he have any abnormal values?",
           expected_context=["JOHN", "SMITH"],
           description="'he' should still be John Smith")
    
    all_passed += t1.passed
    all_failed += t1.failed
    
    # TEST 2: Multi-patient context switching
    print("\n" + "="*80)
    print("TEST 2: CONTEXT SWITCHING - Multiple Patients")
    print("="*80)
    
    t2 = ConversationTest("Context Switching")
    t2.ask("Show Barbara Gordon's vitals", description="Initial: Barbara Gordon")
    t2.ask("What about Robert Chen?",
           expected_context=["ROBERT", "CHEN"],
           description="Switching to different patient")
    t2.ask("What's his cholesterol?",
           expected_context=["ROBERT", "CHEN", "CHOLESTEROL"],
           description="'his' should be Robert Chen (most recent)")
    
    all_passed += t2.passed
    all_failed += t2.failed
    
    # TEST 3: Narrowing down results
    print("\n" + "="*80)
    print("TEST 3: NARROWING DOWN - Filtering Previous Results")
    print("="*80)
    
    t3 = ConversationTest("Narrowing Down")
    t3.ask("Show all patients with abnormal results", description="Broad query")
    t3.ask("Which of them have high glucose?",
           expected_context=["GLUCOSE"],
           description="'them' = patients from previous query")
    t3.ask("Show their blood pressure",
           expected_context=["BLOOD", "PRESSURE"],
           description="'their' = patients with high glucose")
    
    all_passed += t3.passed
    all_failed += t3.failed
    
    # TEST 4: Referential expressions
    print("\n" + "="*80)
    print("TEST 4: REFERENTIAL EXPRESSIONS - That/Those/These")
    print("="*80)
    
    t4 = ConversationTest("Referential Expressions")
    t4.ask("Show recent lab results", description="General query")
    t4.ask("Which of those are abnormal?",
           description="'those' = recent lab results")
    t4.ask("Who do they belong to?",
           description="'they' = abnormal results")
    
    all_passed += t4.passed
    all_failed += t4.failed
    
    # TEST 5: Long conversation chain
    print("\n" + "="*80)
    print("TEST 5: LONG CHAIN - 5+ Turn Conversation")
    print("="*80)
    
    t5 = ConversationTest("Long Chain")
    t5.ask("Show me all patients", description="Turn 1: All patients")
    t5.ask("Who has high glucose?",
           expected_context=["GLUCOSE"],
           description="Turn 2: Filter by glucose")
    t5.ask("What's their average value?",
           description="Turn 3: Stats on filtered patients")
    t5.ask("Are any of them critical?",
           description="Turn 4: Further filtering")
    t5.ask("Show me their full results",
           description="Turn 5: Expand details")
    
    all_passed += t5.passed
    all_failed += t5.failed
    
    # TEST 6: Implicit context (no pronouns)
    print("\n" + "="*80)
    print("TEST 6: IMPLICIT CONTEXT - Assumed Subject")
    print("="*80)
    
    t6 = ConversationTest("Implicit Context")
    t6.ask("Show Barbara Gordon's vitals", description="Establish subject")
    t6.ask("What about blood pressure?",
           expected_context=["BARBARA", "GORDON", "BLOOD", "PRESSURE"],
           description="No pronoun, but should assume same patient")
    t6.ask("And heart rate?",
           expected_context=["BARBARA", "GORDON", "HEART"],
           description="'And' implies continuation")
    
    all_passed += t6.passed
    all_failed += t6.failed
    
    # TEST 7: Temporal context
    print("\n" + "="*80)
    print("TEST 7: TEMPORAL CONTEXT - Time References")
    print("="*80)
    
    t7 = ConversationTest("Temporal Context")
    t7.ask("Show recent observations", description="Initial time-based query")
    t7.ask("Any abnormal ones?",
           description="'ones' = recent observations")
    t7.ask("Who were they for?",
           description="'they' = abnormal recent observations")
    
    all_passed += t7.passed
    all_failed += t7.failed
    
    # TEST 8: Disambiguation
    print("\n" + "="*80)
    print("TEST 8: DISAMBIGUATION - Clarifying Questions")
    print("="*80)
    
    t8 = ConversationTest("Disambiguation")
    t8.ask("Show me patients named Smith", description="Multiple potential matches")
    t8.ask("Show the male one",
           expected_context=["SMITH"],
           description="Narrowing by gender")
    t8.ask("What are his results?",
           expected_context=["SMITH"],
           description="Referring to refined selection")
    
    all_passed += t8.passed
    all_failed += t8.failed
    
    # SUMMARY
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total = all_passed + all_failed
    print(f"\nTotal Queries: {total}")
    print(f"Passed: {all_passed}")
    print(f"Failed: {all_failed}")
    
    if total > 0:
        success_rate = (all_passed / total) * 100
        print(f"Success Rate: {success_rate:.1f}%")
    
    print("\nTest Breakdown:")
    print(f"  Test 1 (Pronoun Resolution): Passed {t1.passed}, Failed {t1.failed}")
    print(f"  Test 2 (Context Switching): Passed {t2.passed}, Failed {t2.failed}")
    print(f"  Test 3 (Narrowing Down): Passed {t3.passed}, Failed {t3.failed}")
    print(f"  Test 4 (Referential Expr.): Passed {t4.passed}, Failed {t4.failed}")
    print(f"  Test 5 (Long Chain): Passed {t5.passed}, Failed {t5.failed}")
    print(f"  Test 6 (Implicit Context): Passed {t6.passed}, Failed {t6.failed}")
    print(f"  Test 7 (Temporal Context): Passed {t7.passed}, Failed {t7.failed}")
    print(f"  Test 8 (Disambiguation): Passed {t8.passed}, Failed {t8.failed}")
    
    if all_failed == 0 and all_passed > 0:
        print("\n[SUCCESS] All conversational memory tests passed!")
    elif all_failed > 0:
        print(f"\n[PARTIAL] {all_failed} tests failed, may need context improvements")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
