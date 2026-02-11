
import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
# Force UTF-8 encoding
sys.stdout.reconfigure(encoding='utf-8')

from app.healthcare_agent import HealthcareAgent
from app.db import get_connection, DB_PATH

def seed_data():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()
    # We DO NOT seed Sarah Jenkins or John Smith to test the "bad UX" hypothesis.
    # We DO seed a patient for "Highest Heart Rate"
    cursor.execute("INSERT OR REPLACE INTO hl7_messages (id, patient_id, patient_first_name, patient_last_name) VALUES (8888, 'P-HIGH', 'HIGH', 'HEART')")
    cursor.execute("INSERT OR REPLACE INTO observations (message_id, display, value_num, unit, observation_datetime) VALUES (8888, 'Heart Rate', 180, 'bpm', '2026-02-10 12:00:00')")
    conn.commit()
    conn.close()

async def test_query(query):
    print(f"\n--- Testing: '{query}' ---")
    agent = HealthcareAgent()
    response = agent.run(query)
    print(f"Answer: {response.answer}")

async def main():
    seed_data()
    # 1. Sarah Johnson (Correct Name)
    await test_query("Analyze blood pressure trends for Sarah Johnson")
    # 2. John Smith (Should exist now)
    await test_query("What is John Smith's latest glucose?")
    # 3. Highest Heart Rate (Should work)
    await test_query("Who has the highest heart rate?")

if __name__ == "__main__":
    asyncio.run(main())
