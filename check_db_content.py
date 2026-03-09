import sqlite3

def check_db():
    conn = sqlite3.connect('agent.db')
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"Tables: {tables}")
        
        # Count patients
        if 'hl7_messages' in tables:
            cursor.execute("SELECT COUNT(DISTINCT patient_id) FROM hl7_messages")
            print(f"Total Patients: {cursor.fetchone()[0]}")
            
            cursor.execute("SELECT patient_id, patient_first_name, patient_last_name FROM hl7_messages LIMIT 5")
            print("Sample Patients:")
            for row in cursor.fetchall():
                print(f"  {row['patient_id']}: {row['patient_first_name']} {row['patient_last_name']}")
        
        # Check observations
        if 'observations' in tables:
            cursor.execute("SELECT COUNT(*) FROM observations")
            print(f"Total Observations: {cursor.fetchone()[0]}")
            
            # Check for critical/worried signs
            # Heart rate > 120, systolic bp > 160, diastolic bp > 100, glucose > 300, A1c > 9, or oxygen saturation < 90
            query = """
            SELECT DISTINCT h.patient_id, h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.unit, o.flag, o.alert_level
            FROM observations o
            JOIN hl7_messages h ON o.message_id = h.id
            WHERE (o.display LIKE '%Heart rate%' AND o.value_num > 120)
            OR (o.display LIKE '%Systolic%' AND o.value_num > 160)
            OR (o.display LIKE '%Diastolic%' AND o.value_num > 100)
            OR (o.display LIKE '%Glucose%' AND o.value_num > 300)
            OR (o.display LIKE '%Hemoglobin A1c%' AND o.value_num > 9)
            OR (o.display LIKE '%Oxygen saturation%' AND o.value_num < 90)
            OR (o.alert_level = 'CRITICAL')
            """
            cursor.execute(query)
            rows = cursor.fetchall()
            print(f"Patients with critical values: {len(rows)}")
            for row in rows:
                print(f"  {row['patient_id']} ({row['patient_first_name']} {row['patient_last_name']}): {row['display']} = {row['value_num']} {row['unit']} ({row['flag']}) [{row['alert_level']}]")

    finally:
        conn.close()

if __name__ == "__main__":
    check_db()
