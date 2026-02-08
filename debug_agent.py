
import sys
import os
import json

# Ensure app is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Set DB Path
db_path = "C:/Users/bradl/Desktop/healthcare_ai_agent/data/healthcare.db"
os.environ["DATABASE_PATH"] = db_path
print(f"Using DB Path: {db_path}")

from app.healthcare_agent import HealthcareAgent

if __name__ == "__main__":
    agent = HealthcareAgent()
    query = "Which patients should I be worried about?"
    print(f"Running Query: {query}")
    
    response = agent.run(query)
    print(f"Answer: {response.answer}")
    print(f"SQL Used: {getattr(response, 'sql_used', 'N/A')}")
    # print(f"Tool Inputs: {response.tool_inputs}") # Removed as attribute doesn't exist
    
    # Check if DB exists
    import sqlite3
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM hl7_messages")
        print(f"DB Row Count: {c.fetchone()[0]}")
        
        c.execute("PRAGMA table_info(hl7_messages)")
        cols = [r[1] for r in c.fetchall()]
        print(f"DB Columns: {cols}")
        conn.close()
    else:
        print("DB File NOT FOUND at content path!")
