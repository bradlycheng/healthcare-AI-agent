
import os
import sys
import sqlite3
from fastapi.testclient import TestClient

# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

# Ensure the password is set in the environment before importing app
os.environ["ADMIN_PASSWORD"] = "d3m0th1s"

from app.api import app
from app.db import get_connection, DB_PATH

client = TestClient(app)

def verify_expert_data_exists():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()
    
    # Check for Diabetic Dave
    cursor.execute("SELECT count(*) FROM hl7_messages WHERE patient_id = 'P-DIABETIC'")
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0

def test_reset_button():
    print("--- Testing Reset Button API (DELETE /messages) ---")
    
    # 1. Reset
    print("Simulating button click (sending DELETE request with password)...")
    # client.delete doesn't support json in some versions, using generic request
    response = client.request("DELETE", "/messages", json={"password": "d3m0th1s"})
    
    if response.status_code == 204:
        print("[OK] API returned 204 No Content (Success)")
    else:
        print(f"[FAIL] API returned {response.status_code}: {response.text}")
        return

    # 2. Verify Data
    print("Verifying database content...")
    if verify_expert_data_exists():
        print("[OK] Expert Scenario data verified in database.")
    else:
        print("[FAIL] Expert Scenario data NOT found after reset!")

if __name__ == "__main__":
    test_reset_button()
