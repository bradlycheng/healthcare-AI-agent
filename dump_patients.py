
import sqlite3
import os

def dump_patient_data(names):
    db_path = "agent.db"
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    query = f"""
    SELECT h.patient_first_name, h.patient_last_name, o.display, o.value_num, o.unit, o.flag, o.alert_level 
    FROM hl7_messages h 
    JOIN observations o ON o.message_id = h.id 
    WHERE (o.alert_level IS NOT NULL OR o.flag NOT IN ('N', ''))
    """
    
    print(f"Executing: {query}")
    cur.execute(query)
    rows = cur.fetchall()
    
    for r in rows:
        print(dict(r))
    
    conn.close()

if __name__ == "__main__":
    dump_patient_data(['SARAH', 'ELIZABETH', 'BOB', 'DAVE', 'CHARLIE'])
