
import requests
import sys
import os
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://healthdataagent.com"

print(f"Target: {BASE_URL}")

def check_deployment():
    print("\n1. Verifying Deployment (checking dashboard.js for debug patch)...")
    try:
        resp = requests.get(f"{BASE_URL}/dashboard.js")
        if resp.status_code == 200:
            if "Failed: ' + err.message" in resp.text:
                print("   [MATCH] Found debug code. New deployment is LIVE.")
            else:
                print("   [WARN] Debug code NOT found. Old version might still be cached or running.")
        else:
            print(f"   [FAIL] Could not fetch dashboard.js: {resp.status_code}")
    except Exception as e:
        print(f"   [ERR] {e}")

def test_reset():
    print("\n2. Testing 'Reset Demo' Endpoint (POST /admin/reset)...")
    try:
        # Increase timeout to distinguish between 504 (Gateway Timeout) and other errors
        password = os.environ.get("ADMIN_PASSWORD")
        resp = requests.post(f"{BASE_URL}/admin/reset", json={"password": password}, timeout=65)
        
        print(f"   Status Code: {resp.status_code}")
        print(f"   Response Text: {resp.text[:500]}") # Print first 500 chars
        
        if resp.status_code == 200:
            print("   [SUCCESS] Reset worked!")
        elif resp.status_code == 504:
            print("   [FAIL] 504 Gateway Timeout. The operation took too long for the load balancer.")
        elif resp.status_code == 502:
            print("   [FAIL] 502 Bad Gateway. The server might have crashed.")
        else:
            print(f"   [FAIL] Unexpected error: {resp.reason}")
            
    except requests.exceptions.ReadTimeout:
        print("   [FAIL] Client Timeout (65s). The server is too slow.")
    except Exception as e:
        print(f"   [ERR] {e}")

if __name__ == "__main__":
    check_deployment()
    test_reset()
