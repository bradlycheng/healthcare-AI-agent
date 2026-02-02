
import requests
import json
import time

URL = "http://localhost:8080/api/query"

# Track issues found
issues = []

def test_single_query(question, history, expected_context=None):
    """Test a single query and return results."""
    try:
        resp = requests.post(URL, json={"question": question, "history": history})
        
        if resp.status_code == 429:
            print(f"  [!] RATE LIMITED - waiting 10s...")
            time.sleep(10)
            resp = requests.post(URL, json={"question": question, "history": history})
        
        data = resp.json()
        success = data.get('success', False)
        answer = data.get('answer', '')
        sql = data.get('sql_used', '')
        
        # Check context retention
        context_ok = True
        if expected_context and success:
            if expected_context.upper() not in sql.upper():
                context_ok = False
                issues.append({
                    'question': question,
                    'expected': expected_context,
                    'sql': sql,
                    'issue': 'Context lost - expected term not in SQL'
                })
        
        return {
            'success': success,
            'answer': answer,
            'sql': sql,
            'context_ok': context_ok
        }
    except Exception as e:
        print(f"  [X] ERROR: {e}")
        return None

def main():
    print("="*70)
    print("TARGETED AI QUERY TESTING - SLOW MODE")
    print("="*70)
    
    # Test 1: "Does she have high blood pressure?" after establishing Barbara context
    print("\n[TEST 1] Pronoun + Medical Term Resolution")
    print("-"*70)
    
    history = []
    
    print("Q1: Show me Barbara Gordon's vitals")
    r1 = test_single_query("Show me Barbara Gordon's vitals", history)
    if r1:
        print(f"  SQL: {r1['sql'][:80]}...")
        history.append({"role": "user", "content": "Show me Barbara Gordon's vitals"})
        history.append({"role": "ai", "content": r1['answer']})
        time.sleep(7)
    
    print("\nQ2: Does she have high blood pressure?")
    r2 = test_single_query("Does she have high blood pressure?", history, expected_context="BARBARA")
    if r2:
        print(f"  SQL: {r2['sql']}")
        print(f"  Context OK: {r2['context_ok']}")
        if not r2['context_ok']:
            print(f"  [!] ISSUE: AI should filter for Barbara but SQL is generic")
    
    time.sleep(7)
    
    # Test 2: "Pulse" vs "Heart Rate" terminology
    print("\n[TEST 2] Medical Term Synonyms")  
    print("-"*70)
    
    history2 = []
    print("Q1: Show me Timeline Tester's vitals")
    r3 = test_single_query("Show me Timeline Tester's vitals", history2)
    if r3:
        print(f"  SQL: {r3['sql'][:80]}...")
        history2.append({"role": "user", "content": "Show me Timeline Tester's vitals"})
        history2.append({"role": "ai", "content": r3['answer']})
        time.sleep(7)
    
    print("\nQ2: What's his pulse?")
    r4 = test_single_query("What's his pulse?", history2, expected_context="TIMELINE")
    if r4:
        print(f"  SQL: {r4['sql']}")
        print(f"  Context OK: {r4['context_ok']}")
        # Check if SQL handles "pulse" properly
        if 'PULSE' in r4['sql'].upper() or 'HEART' in r4['sql'].upper():
            print(f"  [+] SQL searches for pulse/heart rate")
        else:
            print(f"  [!] SQL might not handle 'pulse' synonym")
            issues.append({
                'question': "What's his pulse?",
                'sql': r4['sql'],
                'issue': 'May not recognize "pulse" as synonym for heart rate'
            })
    
    # Summary
    print("\n" + "="*70)
    print("ISSUES FOUND")
    print("="*70)
    if issues:
        for i, issue in enumerate(issues, 1):
            print(f"\n[ISSUE {i}]")
            print(f"  Question: {issue['question']}")
            print(f"  Problem: {issue['issue']}")
            print(f"  SQL: {issue['sql']}")
            if 'expected' in issue:
                print(f"  Expected: '{issue['expected']}' in SQL")
    else:
        print("\nNo issues found! All tests passed.")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    main()
