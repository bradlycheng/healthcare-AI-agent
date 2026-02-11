
import asyncio
import os
import sys
import subprocess

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
sys.stdout.reconfigure(encoding='utf-8')

def run_script(script_name):
    print(f"\n{'='*60}")
    print(f"RUNNING: {script_name}")
    print(f"{'='*60}")
    
    # Force UTF-8 for subprocess output reading
    try:
        result = subprocess.run(
            [sys.executable, script_name], 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            check=True
        )
        # Handle printing with potential encoding issues on Windows console
        try:
            print(result.stdout)
        except UnicodeEncodeError:
            print(result.stdout.encode('utf-8', errors='replace').decode('utf-8'))
            
        print(f"✅ {script_name} PASSED")
        return True
    except subprocess.CalledProcessError as e:
        print(e.stdout)
        print(e.stderr)
        print(f"❌ {script_name} FAILED")
        return False

def main():
    print("Starting Comprehensive System Verification...")
    
    results = {}
    
    # 1. Expert Scenarios (Verifies Logic, Tables, Reasoning)
    results["Expert Scenarios"] = run_script("test_expert_scenarios.py")
    
    # 2. Dashboard Examples (Verifies Suggestion Chips)
    results["Dashboard Examples"] = run_script("test_examples.py")
    
    # 3. Reset API (Verifies Data Management & System state)
    # MUST RUN LAST to leave DB in clean "Reset" state
    results["Reset API"] = run_script("test_reset_api.py")
    
    print("\n" + "="*60)
    print("FINAL TEST REPORT")
    print("="*60)
    all_passed = True
    for name, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        icon = "✅" if passed else "❌"
        print(f"{icon} {name}: {status}")
        if not passed:
            all_passed = False
            
    if all_passed:
        print("\n🎉 ALL SYSTEMS GO! The agent is fully verified.")
        sys.exit(0)
    else:
        print("\n⚠️ SOME TESTS FAILED. check logs above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
