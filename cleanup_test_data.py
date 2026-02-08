
import sqlite3

def cleanup():
    conn = sqlite3.connect('agent.db')
    try:
        cur = conn.cursor()
        
        # 1. Start with observations
        print("Cleaning up observations for CRITICAL TEST...")
        cur.execute("DELETE FROM observations WHERE value_num > 103 AND unit='F'")
        print(f"Deleted {cur.rowcount} observations.")
        
        # 2. Cleanup messages based on patient name
        print("Cleaning up messages for CRITICAL TEST...")
        cur.execute("DELETE FROM hl7_messages WHERE patient_first_name = 'CRITICAL'")
        print(f"Deleted {cur.rowcount} messages.")
        
        conn.commit()
    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    cleanup()
