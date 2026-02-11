
import asyncio
import json
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

# Force UTF-8 encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8')

from app.healthcare_agent import HealthcareAgent
from app.db import get_connection, DB_PATH

def seed_scenario_data():
    conn = get_connection(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Diabetic with High Glucose (Data for Scenario 1)
    cursor.execute("INSERT OR REPLACE INTO hl7_messages (id, patient_id, patient_first_name, patient_last_name) VALUES (9001, 'P-DIABETIC', 'DIABETIC', 'DAVE')")
    cursor.execute("INSERT OR REPLACE INTO diagnoses (patient_id, diagnosis_code, diagnosis_name, diagnosis_date, status) VALUES ('P-DIABETIC', 'E11.9', 'Type 2 diabetes mellitus', '2025-01-01', 'Active')")
    cursor.execute("INSERT OR REPLACE INTO observations (message_id, display, value_num, unit, observation_datetime) VALUES (9001, 'Glucose', 250, 'mg/dL', '2026-02-10 10:00:00')")

    # 2. Critical Vitals (Data for Scenario 2) - Already covered by "CRITICAL BOB" in reproduce_issue, but re-adding here
    cursor.execute("INSERT OR REPLACE INTO hl7_messages (id, patient_id, patient_first_name, patient_last_name) VALUES (9999, 'P-CRITICAL', 'CRITICAL', 'BOB')")
    cursor.execute("INSERT OR REPLACE INTO observations (message_id, display, value_num, unit, observation_datetime) VALUES (9999, 'Heart Rate', 135, 'bpm', '2026-02-10 20:00:00')")
    cursor.execute("INSERT OR REPLACE INTO observations (message_id, display, value_num, unit, observation_datetime) VALUES (9999, 'SpO2', 88, '%', '2026-02-10 20:00:00')")

    # 3. Visit with Dr. Chen (Data for Scenario 3)
    cursor.execute("INSERT OR REPLACE INTO hl7_messages (id, patient_id, patient_first_name, patient_last_name) VALUES (9003, 'P-VISIT', 'VISIT', 'VICTOR')")
    cursor.execute("INSERT OR REPLACE INTO visits (visit_id, patient_id, visit_date, provider_name, chief_complaint) VALUES ('V-9003', 'P-VISIT', DATE('now'), 'Dr. Alice Chen', 'Follow-up')")

    # 4. CKD Patient (Data for Scenario 4)
    cursor.execute("INSERT OR REPLACE INTO hl7_messages (id, patient_id, patient_first_name, patient_last_name) VALUES (9004, 'P-CKD', 'CKD', 'CHARLIE')")
    cursor.execute("INSERT OR REPLACE INTO observations (message_id, display, value_num, unit, observation_datetime) VALUES (9004, 'eGFR', 45, 'mL/min/1.73m2', '2026-02-10 09:00:00')")

    conn.commit()
    conn.close()

async def run_scenario(name, query):
    print(f"\n--- SCENARIO: {name} ---")
    print(f"Query: {query}")
    
    agent = HealthcareAgent()
    response = agent.run(query)
    
    print(f"Answer: {response.answer}")
    
    # Print tool results for debugging/verification
    for step in response.reasoning_trace:
        for tr in step.tool_results:
            # summarize large results
            if isinstance(tr.result, dict) and 'results' in tr.result:
                count = len(tr.result['results'])
                print(f"  Tool {tr.tool} retrieved {count} rows.")
                if 'sql' in tr.result:
                    print(f"  SQL: {tr.result['sql']}")
            else:
                print(f"  Tool {tr.tool} result: {str(tr.result)[:100]}...")

async def main():
    seed_scenario_data()

    # 1. Chronic Disease Management
    # Logic in seed: Diabetics have Glucose 110-250.
    # Note: Explicitly asking for "patients with diabetes AND glucose > 150" to be more likely to find matches.
    await run_scenario(
        "Chronic Disease (Diabetes Control)", 
        "Show me all patients who have diabetes AND have Glucose greater than 150."
    )

    # 2. Vitals Monitoring (Risk Stratification)
    # Logic in seed: Random abnormals are generated.
    await run_scenario(
        "Vitals Monitoring (Critical)", 
        "Which patients have critical vitals (HR > 100 or SpO2 < 95)?"
    )

    # 3. Visit History
    # Logic in seed: Providers include "Dr. Alice Chen". Visits are "recent".
    # Using "Dr." to match any doctor since specific names are random.
    await run_scenario(
        "Visit History (Provider)", 
        "Show me all patients seen by any doctor (Dr.) recently."
    )

    # 4. Kidney Function (CKD)
    # Logic in seed: CKD patients have eGFR 30-59.
    # Rephrasing to avoid calculator confusion: "Show list of patients..."
    await run_scenario(
        "Kidney Function (CKD)", 
        "Show list of patients with eGFR < 60."
    )

if __name__ == "__main__":
    asyncio.run(main())
