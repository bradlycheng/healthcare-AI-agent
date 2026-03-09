
import sqlite3
import os

def check_charlie():
    db_path = "agent.db"
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("Checking hl7_messages for 'Charlie'...")
    cur.execute("SELECT id, patient_first_name, patient_last_name FROM hl7_messages WHERE patient_first_name = 'CKD' OR patient_last_name = 'Charlie'")
    rows = cur.fetchall()
    for row in rows:
        print(row)
        
    print("\nChecking observations for Charlie's eGFR...")
    # Get Charlie's message IDs
    ids = [row[0] for row in rows]
    if ids:
        placeholders = ','.join(['?'] * len(ids))
        cur.execute(f"SELECT * FROM observations WHERE message_id IN ({placeholders})", ids)
        obs = cur.fetchall()
        for o in obs:
            print(o)
    else:
        print("No Charlie found in hl7_messages.")

    conn.close()

if __name__ == "__main__":
    check_charlie()
