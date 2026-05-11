
import requests
import time
import sys
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "http://localhost:8080"

def wait_for_service():
    print("Waiting for service...")
    for i in range(30):
        try:
            resp = requests.get(f"{BASE_URL}/ping", timeout=2)
            if resp.status_code == 200:
                print("Service Up!")
                return
        except:
            time.sleep(1)
            print(".", end="", flush=True)
    print("Service Timeout")
    sys.exit(1)

def trigger_reset():
    print("Resetting database to Day 1 state...")
    try:
        password = os.environ.get("ADMIN_PASSWORD")
        resp = requests.post(f"{BASE_URL}/admin/reset", json={"password": password}, timeout=60)
        print(f"Reset Response: {resp.status_code}")
        if resp.status_code == 200:
            print("Reset Success!")
        elif resp.status_code == 409:
            print("Reset already running (clean state imminent)")
        else:
            print(f"Reset Failed: {resp.text}")
    except Exception as e:
        print(f"Note: Reset request timed out or failed ({e}), but likely running in background.")

if __name__ == "__main__":
    wait_for_service()
    trigger_reset()
