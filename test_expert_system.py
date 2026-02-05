
import threading
import requests
import time
import random
import sys
import io

# Force utf-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_URL = "http://localhost:8080"
THREADS = 10
ITERATIONS = 5

RESULTS = {"success": 0, "fail": 0, "errors": []}

def log(msg):
    print(f"[{threading.current_thread().name}] {msg}")

def send_hl7_message(i):
    # Sends a message with unique ID to track it
    val = random.randint(70, 150)
    flag = 'H' if val > 140 else 'N'
    
    msg = f"""MSH|^~\\&|TEST|StressTest|LIS|LAB|202401201200||ORU^R01|MSG_STRESS_{i}|P|2.5
PID|1||PAT_{i}||STRESS^USER_{i}||19800101|M
OBR|1|ORD{i}|RES{i}|PANEL^Test|||202401201200
OBX|1|NM|2345-7^GLUCOSE||{val}|mg/dL|70-100|{flag}|||F"""
    
    try:
        r = requests.post(f"{API_URL}/oru/parse", json={"hl7_text": msg, "use_llm": False, "persist": True}, timeout=5)
        if r.status_code == 200:
            return True, None
        return False, f"Status {r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

def query_api():
    try:
        r = requests.post(f"{API_URL}/api/query", json={"question": "count patients"}, timeout=5)
        if r.status_code == 200:
            return True, None
        # 429 is expected rate limiting, consider it 'handled'
        if r.status_code == 429:
            return True, "Rate Limited (Expected)"
        return False, f"Status {r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

def worker(idx):
    for j in range(ITERATIONS):
        # Mix of writes (HL7) and reads (Query)
        if random.random() > 0.5:
            ok, err = send_hl7_message(f"{idx}_{j}")
            action = "HL7"
        else:
            ok, err = query_api()
            action = "QUERY"
        
        if ok:
            RESULTS["success"] += 1
            if err: log(f"{action} OK but: {err}")
        else:
            RESULTS["fail"] += 1
            RESULTS["errors"].append(f"{action} Fail: {err}")
            log(f"{action} FAILED: {err}")
            
        time.sleep(random.random() * 0.5) # Random delay

def chaos_reset():
    # Attempt to reset DB in middle of test
    time.sleep(2)
    log("!!! TRIGGERING CHAOS RESET !!!")
    try:
        r = requests.post(f"{API_URL}/admin/reset", timeout=15)
        log(f"Reset Result: {r.status_code}")
    except Exception as e:
        log(f"Reset Failed: {e}")

def main():
    print(f"Starting Expert Stress Test: {THREADS} threads, {ITERATIONS} iterations each.")
    
    threads = []
    
    # Start workers
    for i in range(THREADS):
        t = threading.Thread(target=worker, args=(i,), name=f"Worker-{i}")
        threads.append(t)
        t.start()
        
    # Start chaos monkey
    chaos = threading.Thread(target=chaos_reset, name="ChaosMonkey")
    chaos.start()
    threads.append(chaos)
    
    # Wait for all
    for t in threads:
        t.join()
        
    print("\n" + "="*50)
    print(f"STRESS TEST RESULTS")
    print(f"Total Operations: {RESULTS['success'] + RESULTS['fail']}")
    print(f"Success: {RESULTS['success']}")
    print(f"Failed: {RESULTS['fail']}")
    
    if RESULTS['fail'] > 0:
        print("Sample Errors:")
        for e in RESULTS['errors'][:5]:
            print(f" - {e}")
            
    print("="*50)
    
    return RESULTS['fail'] == 0

if __name__ == "__main__":
    main()
