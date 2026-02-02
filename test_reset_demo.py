import requests
import sqlite3
import time

# Wait for server to start
print("Waiting for server...")
time.sleep(5)

# Test reset endpoint
print("\n" + "="*80)
print("TESTING RESET DEMO FUNCTIONALITY")
print("="*80)

try:
    print("\nCalling /admin/reset endpoint...")
    resp = requests.post("http://localhost:8080/admin/reset")
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
except Exception as e:
    print(f"Error: {e}")

# Wait for reset to complete
time.sleep(3)

# Verify database content
print("\n" + "="*80)
print("VERIFYING NEW SAMPLE DATA")
print("="*80)

conn = sqlite3.connect("agent.db")
cursor = conn.cursor()

# Count patients
cursor.execute("SELECT COUNT(DISTINCT patient_id) FROM hl7_messages")
patient_count = cursor.fetchone()[0]
print(f"\nTotal Patients: {patient_count}")

# Count observations
cursor.execute("SELECT COUNT(*) FROM observations")
obs_count = cursor.fetchone()[0]
print(f"Total Observations: {obs_count}")

# Sample observations
print("\nSample Observations:")
cursor.execute("""
    SELECT h.patient_first_name || ' ' || h.patient_last_name as name,
           o.display, o.value_num, o.unit, o.flag
    FROM hl7_messages h
    JOIN observations o ON h.id = o.message_id
    WHERE o.value_num IS NOT NULL
    ORDER BY h.patient_id, o.id
    LIMIT 15
""")
for row in cursor.fetchall():
    flag = f" [{row[4]}]" if row[4] else ""
    print(f"  {row[0]:<25} {row[1]:<20} {row[2]} {row[3] or ''}{flag}")

# Show patient diversity
print("\n" + "="*80)
print("PATIENT DIVERSITY")
print("="*80)
cursor.execute("""
    SELECT h.patient_first_name || ' ' || h.patient_last_name as name,
           h.patient_sex,
           CAST(strftime('%Y', 'now') AS INTEGER) - CAST(substr(h.patient_dob, 1, 4) AS INTEGER) as age,
           COUNT(o.id) as obs_count
    FROM hl7_messages h
    LEFT JOIN observations o ON h.id = o.message_id
    GROUP BY h.patient_id
    ORDER BY name
""")
print(f"\n{'Name':<25} {'Sex':<5} {'Age':<5} {'Observations'}")
print("-" * 80)
for row in cursor.fetchall():
    print(f"{row[0]:<25} {row[1]:<5} {row[2]:<5} {row[3]}")

# Check for longitudinal data (same patient, multiple visits)
print("\n" + "="*80)
print("LONGITUDINAL DATA CHECK")
print("="*80)
cursor.execute("""
    SELECT patient_first_name || ' ' || patient_last_name as name,
           COUNT(*) as visit_count
    FROM hl7_messages
    GROUP BY patient_id
    HAVING COUNT(*) > 1
    ORDER BY visit_count DESC
""")
print("\nPatients with Multiple Visits:")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]} visits")

# Show clinical conditions represented
print("\n" + "="*80)
print("CLINICAL CONDITIONS REPRESENTED")
print("="*80)
cursor.execute("""
    SELECT DISTINCT
        CASE 
            WHEN content LIKE '%Diabetes%' THEN 'Diabetes'
            WHEN content LIKE '%Hypertension%' OR content LIKE '%BP%' THEN 'Hypertension'
            WHEN content LIKE '%Cardiac%' OR content LIKE '%TROPONIN%' OR content LIKE '%MI%' THEN 'Cardiac'
            WHEN content LIKE '%Anemia%' THEN 'Anemia'
            WHEN content LIKE '%Thyroid%' THEN 'Thyroid'
            WHEN content LIKE '%Kidney%' OR content LIKE '%CKD%' OR content LIKE '%Renal%' THEN 'Kidney Disease'
            WHEN content LIKE '%COPD%' OR content LIKE '%Respiratory%' THEN 'Respiratory'
            WHEN content LIKE '%Gout%' THEN 'Gout'
            WHEN content LIKE '%Metabolic%' THEN 'Metabolic Syndrome'
            WHEN content LIKE '%Healthy%' OR content LIKE '%normal limits%' THEN 'Healthy'
            ELSE 'Other'
        END as condition
    FROM observations
    WHERE display = 'Clinical Note'
""")
conditions = [row[0] for row in cursor.fetchall() if row[0] != 'Other']
print("\nConditions in sample data:")
for cond in sorted(set(conditions)):
    print(f"  - {cond}")

conn.close()

print("\n" + "="*80)
print("VERIFICATION COMPLETE")
print("="*80)
