
import asyncio
import json
import sys
from app.healthcare_agent import HealthcareAgent

sys.stdout.reconfigure(encoding='utf-8')

async def run_test(name, query, expected_keywords, expected_acuity=None):
    print(f"\n[TEST] {name}")
    print(f"Query: {query}")
    agent = HealthcareAgent()
    response = agent.run(query)
    
    answer = response.answer
    highlights = response.highlights
    
    print("-" * 20 + " ANSWER " + "-" * 20)
    print(answer)
    print("-" * 20 + " HIGHLIGHTS " + "-" * 20)
    for h in highlights:
        print(f"• {h}")
    print("-" * 48)
    
    # Assertions
    all_found = True
    for kw in expected_keywords:
        if kw.lower() not in answer.lower() and not any(kw.lower() in h.lower() for h in highlights):
            print(f"❌ MISSING KEYWORD: {kw}")
            all_found = False
            
    has_table = "|" in answer and "Patient" in answer
    if len(expected_keywords) >= 2 and not has_table:
        print("⚠️  MISSING TABLE for multi-patient response")
        
    if all_found:
        print(f"✅ PASSED: {name}")
    else:
        print(f"❌ FAILED: {name}")
    return all_found

async def main():
    print("=== Healthcare AI Agent Platform Regression Suite ===")
    
    results = []
    
    # 1. Expert Scenario: Critical Bob
    results.append(await run_test(
        "Critical Bob Detection",
        "How is Critical Bob doing?",
        ["Bob", "Critical", "135", "88"]
    ))
    
    # 2. Expert Scenario: Diabetic Dave
    results.append(await run_test(
        "Diabetic Dave Trends",
        "Show me Diabetic Dave's glucose history.",
        ["Dave", "Glucose", "250"]
    ))
    
    # 3. Multi-patient Table Test
    results.append(await run_test(
        "Multi-patient Table Rendering",
        "Which patients should I be worried about?",
        ["Bob", "Miller", "Critical", "Warning", "Sarah"]
    ))
    
    # 4. Chronic Disease Focus
    results.append(await run_test(
        "CKD Analysis",
        "Who has stage 3 chronic kidney disease and what is their eGFR?",
        ["Charlie", "Stage 3", "45"]
    ))

    # Summary
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n=== OVERALL RESULT: {passed}/{total} Passed ===")
    
    if passed < total:
        print("❌ Regression suite failed. Investigation required.")
        sys.exit(1)
    else:
        print("🎉 All systems verified and consistent.")

if __name__ == "__main__":
    asyncio.run(main())
