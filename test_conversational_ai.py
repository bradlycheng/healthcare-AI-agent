
import requests
import json
import time

URL = "http://localhost:8080/api/query"

def test_conversation(scenario_name, questions):
    """
    Test a conversational flow with multiple questions.
    questions = [(question_text, expected_context_patient), ...]
    """
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario_name}")
    print('='*60)
    
    history = []
    
    for i, (question, expected_patient) in enumerate(questions, 1):
        print(f"\nQ{i}: {question}")
        
        if i > 1:
            # Wait to avoid rate limit
            time.sleep(6)
        
        try:
            resp = requests.post(URL, json={"question": question, "history": history})
            data = resp.json()
            
            if resp.status_code == 429:
                print(f"  [!] RATE LIMITED")
                return
            
            success = data.get('success', False)
            answer = data.get('answer', 'No answer')
            sql = data.get('sql_used', '')
            error = data.get('error')
            
            print(f"  [OK] SUCCESS: {success}")
            print(f"  ANSWER: {answer[:100]}...")
            print(f"  SQL: {sql}")
            
            if error:
                print(f"  [!] ERROR: {error}")
            
            # Check if expected patient is in SQL
            if expected_patient and success:
                patient_upper = expected_patient.upper()
                if patient_upper in sql.upper():
                    print(f"  [+] Context retained: Found '{expected_patient}' in SQL")
                else:
                    print(f"  [-] Context LOST: Expected '{expected_patient}' not in SQL")
            
            # Add to history
            history.append({"role": "user", "content": question})
            history.append({"role": "ai", "content": answer})
            
        except Exception as e:
            print(f"  [X] EXCEPTION: {e}")
            return

def main():
    print("="*60)
    print("AI QUERY ASSISTANT - COMPREHENSIVE TEST SUITE")
    print("="*60)
    
    # Test 1: Simple follow-up with pronoun
    test_conversation(
        "Simple Pronoun Resolution",
        [
            ("Show me Barbara Gordon's vitals", "Barbara"),
            ("What's her heart rate?", "Barbara"),
            ("Does she have high blood pressure?", "Barbara")
        ]
    )
    
    # Test 2: Medical term variations
    test_conversation(
        "Medical Term Variations",
        [
            ("Who has elevated glucose?", None),
            ("What about their cholesterol?", None),  # Should understand "their" = patients with high glucose
        ]
    )
    
    # Test 3: Multiple patients, then narrow down
    test_conversation(
        "Narrowing Patient Search",
        [
            ("Show all patients", None),
            ("Which ones have abnormal results?", None),
            ("What about John Smith specifically?", "John Smith"),
            ("What's his glucose level?", "John Smith")
        ]
    )
    
    # Test 4: Temporal follow-up
    test_conversation(
        "Temporal Context",
        [
            ("Show recent messages", None),
            ("Any critical alerts in those?", None),
        ]
    )
    
    # Test 5: Vital signs variations
    test_conversation(
        "Vital Signs Name Matching",
        [
            ("Show me Timeline Tester's blood pressure", "Timeline"),
            ("What about his pulse?", "Timeline"),  # Testing "pulse" vs "heart rate"
        ]
    )
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
