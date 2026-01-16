
import sqlite3
import os
from datetime import datetime, timedelta
from app.db import init_db, insert_message_and_observations, prune_messages, delete_all_messages, DB_PATH

def test_features():
    print("Testing Database Features...")
    
    # 1. Reset
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()
    
    # 2. Insert "Old" Message (3 days ago)
    old_date = (datetime.utcnow() - timedelta(days=3)).isoformat()
    insert_message_and_observations(
        raw_hl7="MSH|^~\\&|OLD",
        received_at=old_date,
        patient={"id": "old-1"}
    )
    
    # 3. Insert "New" Message (Today)
    new_date = datetime.utcnow().isoformat()
    insert_message_and_observations(
        raw_hl7="MSH|^~\\&|NEW",
        received_at=new_date,
        patient={"id": "new-1"}
    )
    
    # Verify count = 2
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT count(*) FROM hl7_messages").fetchone()[0]
    conn.close()
    print(f"Initial count: {count} (Expected 2)")
    assert count == 2
    
    # 4. Test Pruning (Keep 2 days)
    print("Running prune_messages(days_to_keep=2)...")
    deleted = prune_messages(days_to_keep=2)
    print(f"Deleted: {deleted} (Expected 1)")
    
    # Verify count = 1
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT patient_id FROM hl7_messages").fetchall()
    conn.close()
    print("REMAINING IDs: {[r[0] for r in rows]}")
    assert len(rows) == 1
    assert rows[0][0] == "new-1"
    print("Pruning Logic: PASS")
    
    # 5. Test Reset (Clear + Seed)
    print("Running reset via delete_all_messages_endpoint logic...")
    # NOTE: The API endpoint logic calls delete then seed. 
    # Here we simulate what the API does.
    delete_all_messages()
    from app.seed import seed_database
    seed_database(verbose=False)
    
    conn = sqlite3.connect(DB_PATH)
    count = conn.execute("SELECT count(*) FROM hl7_messages").fetchone()[0]
    conn.close()
    print(f"Final count: {count} (Expected 8)")
    assert count == 8
    print("Reset Demo Logic: PASS")

if __name__ == "__main__":
    try:
        test_features()
        print("\nAll tests passed successfully!")
    except AssertionError as e:
        print(f"\nTest Failed: {e}")
    except Exception as e:
        print(f"\nVerify Error: {e}")
