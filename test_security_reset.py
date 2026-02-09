
import requests
import sys

BASE_URL = "http://localhost:8000"

def test_reset_security():
    print("--- Testing Security for DELETE /messages ---")
    
    # 1. Test Config: No Payload (Should fail 422 Unprocessable Entity - Pydantic validation)
    print("\n1. Testing NO password payload...")
    try:
        resp = requests.delete(f"{BASE_URL}/messages")
        if resp.status_code == 422:
            print("PASS: Rejected missing payload (422).")
        else:
            print(f"FAIL: Expected 422, got {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"FAIL: Exception {e}")

    # 2. Test Invalid Password
    print("\n2. Testing INVALID password...")
    try:
        resp = requests.delete(f"{BASE_URL}/messages", json={"password": "wrongpass"})
        if resp.status_code == 401:
            print("PASS: Rejected invalid password (401).")
        else:
            print(f"FAIL: Expected 401, got {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"FAIL: Exception {e}")

    # 3. Test Valid Password
    print("\n3. Testing VALID password ('demo-reset')...")
    try:
        resp = requests.delete(f"{BASE_URL}/messages", json={"password": "demo-reset"})
        if resp.status_code == 204:
            print("PASS: Accepted valid password (204).")
        else:
            print(f"FAIL: Expected 204, got {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"FAIL: Exception {e}")

    # 4. Test User Requested Password ('d3m0th1s')
    print("\n4. Testing USER REQUESTED password ('d3m0th1s')...")
    try:
        resp = requests.delete(f"{BASE_URL}/messages", json={"password": "d3m0th1s"})
        if resp.status_code == 204:
            print("PASS: Accepted 'd3m0th1s' (204).")
        else:
            print(f"FAIL: Expected 204, got {resp.status_code}")
            print(resp.text)
    except Exception as e:
        print(f"FAIL: Exception {e}")

if __name__ == "__main__":
    test_reset_security()
