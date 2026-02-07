import sqlite3
conn = sqlite3.connect('agent.db')
conn.row_factory = sqlite3.Row

# Check hl7_messages.patient_id values
print("=== hl7_messages sample ===")
rows = conn.execute("SELECT id, patient_id, patient_first_name, patient_last_name FROM hl7_messages LIMIT 5").fetchall()
for r in rows:
    print(f"  ID:{r['id']} patient_id:'{r['patient_id']}' name:{r['patient_first_name']} {r['patient_last_name']}")

print("\n=== Non-empty patient_ids in hl7_messages ===")
rows = conn.execute("SELECT COUNT(*) as cnt FROM hl7_messages WHERE patient_id IS NOT NULL AND patient_id != ''").fetchone()
print(f"Count: {rows['cnt']}")

print("\n=== Empty patient_ids in hl7_messages ===")
rows = conn.execute("SELECT COUNT(*) as cnt FROM hl7_messages WHERE patient_id IS NULL OR patient_id = ''").fetchone()
print(f"Count: {rows['cnt']}")
