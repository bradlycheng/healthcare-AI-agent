"""
Additional Test Suites for Healthcare AI Agent
- HL7 Message Processing
- Alert System
- RAG Document Retrieval
- Clinical Scenarios
- Performance Tests
"""
import sys
import io
import time
import sqlite3
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

RESULTS = {"passed": 0, "failed": 0}

def test(name, passed, details=""):
    RESULTS["passed" if passed else "failed"] += 1
    symbol = "[OK]" if passed else "[FAIL]"
    print(f"  {symbol} {name}" + (f" - {details}" if details else ""))

def header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

# =============================================================================
# 1. HL7 MESSAGE PROCESSING TESTS
# =============================================================================
def test_hl7_processing():
    header("1. HL7 MESSAGE PROCESSING TESTS")
    
    from app.hl7_parser import parse_oru
    
    # Test valid ORU message
    valid_oru = """MSH|^~\\&|HIS|HOSPITAL|LIS|LAB|202501281200||ORU^R01|MSG12345|P|2.5
PID|1||P12345||DOE^JOHN||19800515|M
OBR|1|ORD001|RES001|GLUC^Glucose|||202501281200
OBX|1|NM|2345-7^GLUCOSE||126|mg/dL|70-100|H|||F"""
    
    try:
        patient, observations = parse_oru(valid_oru)
        test("Parse valid ORU message", patient is not None)
        test("Extract patient ID", patient.get("id") == "P12345")
        test("Extract patient name", "DOE" in str(patient.get("last_name", "")))
        test("Extract observation value", len(observations) > 0)
    except Exception as e:
        test("HL7 Parsing", False, str(e))
    
    # Test message with clinical notes
    note_oru = """MSH|^~\\&|HIS|HOSPITAL|LIS|LAB|202501281200||ORU^R01|MSG12346|P|2.5
PID|1||P12346||SMITH^JANE||19900101|F
OBR|1|ORD002|RES002|LAB^Lab Panel|||202501281200
OBX|1|TX|NOTE^Clinical Note||Patient reports fatigue and weight loss.||||||F"""
    
    try:
        patient, observations = parse_oru(note_oru)
        has_tx_obs = any(o.get("value_type") == "TX" for o in observations)
        test("Parse TX (text) observations", has_tx_obs)
    except Exception as e:
        test("TX observation parsing", False, str(e))
    
    # Test invalid message
    invalid_msg = "This is not an HL7 message"
    try:
        patient, observations = parse_oru(invalid_msg)
        # Should either return None/empty or raise an exception
        test("Reject invalid message", False, "Should have raised exception")
    except:
        test("Reject invalid message", True, "Exception raised as expected")

# =============================================================================
# 2. ALERT SYSTEM TESTS
# =============================================================================
def test_alert_system():
    header("2. ALERT SYSTEM TESTS")
    
    from app.alerts import check_alert, CLINICAL_RULES
    
    # Test high glucose alert
    alert = check_alert("2345-7", 200)  # Very high glucose
    test("High glucose triggers alert", alert is not None and "glucose" in alert.get("message", "").lower())
    
    # Test critical troponin alert
    alert = check_alert("49563-0", 0.5)  # Elevated troponin
    test("Elevated troponin triggers alert", alert is not None)
    
    # Test normal values (no alert)
    alert = check_alert("2345-7", 85)  # Normal glucose
    test("Normal glucose no alert", alert is None)
    
    # Test potassium alert
    alert = check_alert("6298-4", 6.0)  # High potassium
    test("High potassium triggers alert", alert is not None)
    
    # Test alert rules exist
    test("Alert rules configured", len(CLINICAL_RULES) > 0, f"{len(CLINICAL_RULES)} rules")

# =============================================================================
# 3. RAG DOCUMENT RETRIEVAL TESTS
# =============================================================================
def test_rag_retrieval():
    header("3. RAG DOCUMENT RETRIEVAL TESTS")
    
    try:
        from app.vector_store import search, get_document_count
        
        doc_count = get_document_count()
        test("Documents indexed", doc_count > 0, f"{doc_count} docs")
        
        # Test glucose-related search
        results = search("What is normal glucose level?", top_k=3)
        has_results = results and results.get("documents") and len(results["documents"][0]) > 0
        test("Glucose query returns results", has_results)
        
        # Test blood pressure search
        results = search("hypertension blood pressure treatment", top_k=3)
        has_bp_results = results and results.get("documents") and len(results["documents"][0]) > 0
        test("Blood pressure query returns results", has_bp_results)
        
        # Test relevance (distances should be reasonable)
        if results and results.get("distances"):
            min_distance = min(results["distances"][0]) if results["distances"][0] else 1.0
            test("Search returns relevant results", min_distance < 0.8, f"min_distance={min_distance:.2f}")
        
    except ImportError as e:
        test("RAG module available", False, str(e))
    except Exception as e:
        test("RAG search functional", False, str(e))

# =============================================================================
# 4. CLINICAL SCENARIO TESTS
# =============================================================================
def test_clinical_scenarios():
    header("4. CLINICAL SCENARIO TESTS")
    
    from app.query_assistant import process_query
    
    scenarios = [
        # Diabetes management
        ("Show me all diabetic patients on Metformin", 
         lambda r: r["success"] and r["row_count"] > 0),
        
        # Critical value identification
        ("Which patients have critical lab values?",
         lambda r: r["success"]),
        
        # Medication reconciliation
        ("Show medications for patients with hypertension",
         lambda r: r["success"]),
        
        # Follow-up needed
        ("Show patients who haven't had a visit in 30 days",
         lambda r: r["success"]),
        
        # Lab trends (time-based)
        ("Show glucose trends for diabetic patients",
         lambda r: r["success"]),
    ]
    
    for question, validator in scenarios:
        try:
            result = process_query(question)
            passed = validator(result)
            test(question[:40] + "...", passed, f"rows={result.get('row_count', 0)}")
        except Exception as e:
            test(question[:40] + "...", False, str(e)[:50])

# =============================================================================
# 5. PERFORMANCE TESTS
# =============================================================================
def test_performance():
    header("5. PERFORMANCE TESTS")
    
    from app.query_assistant import process_query
    
    # Test query response time
    start = time.time()
    result = process_query("Show all patients")
    elapsed = time.time() - start
    test(f"Query response time", elapsed < 10, f"{elapsed:.2f}s")
    
    # Test database query speed
    DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
    start = time.time()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("SELECT COUNT(*) FROM observations").fetchone()
    conn.close()
    db_time = time.time() - start
    test(f"Database query speed", db_time < 0.5, f"{db_time*1000:.1f}ms")
    
    # Test memory of large result set
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT * FROM observations LIMIT 1000").fetchall()
        conn.close()
        test("Large result set handling", len(rows) > 0, f"{len(rows)} rows")
    except Exception as e:
        test("Large result set handling", False, str(e))

# =============================================================================
# 6. DATA CONSISTENCY TESTS
# =============================================================================
def test_data_consistency():
    header("6. DATA CONSISTENCY TESTS")
    
    DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
    conn = sqlite3.connect(DB_PATH)
    
    # Test foreign key integrity
    orphan_obs = conn.execute("""
        SELECT COUNT(*) FROM observations o
        LEFT JOIN hl7_messages h ON o.message_id = h.id
        WHERE h.id IS NULL
    """).fetchone()[0]
    test("No orphan observations", orphan_obs == 0, f"{orphan_obs} orphans")
    
    # Test medication patient references
    invalid_meds = conn.execute("""
        SELECT COUNT(*) FROM medications m
        WHERE m.patient_id NOT IN (SELECT DISTINCT patient_id FROM hl7_messages)
    """).fetchone()[0]
    test("Medication references valid", invalid_meds == 0, f"{invalid_meds} invalid")
    
    # Test diagnosis patient references
    invalid_diag = conn.execute("""
        SELECT COUNT(*) FROM diagnoses d
        WHERE d.patient_id NOT IN (SELECT DISTINCT patient_id FROM hl7_messages)
    """).fetchone()[0]
    test("Diagnosis references valid", invalid_diag == 0, f"{invalid_diag} invalid")
    
    # Test date formats are consistent
    bad_dates = conn.execute("""
        SELECT COUNT(*) FROM hl7_messages 
        WHERE patient_dob NOT GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'
        AND patient_dob IS NOT NULL AND patient_dob != ''
    """).fetchone()[0]
    test("DOB format consistent", bad_dates == 0, f"{bad_dates} bad dates")
    
    conn.close()

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + "="*60)
    print(" ADDITIONAL SYSTEM TESTS")
    print(" Healthcare AI Agent")
    print("="*60)
    
    test_hl7_processing()
    test_alert_system()
    test_rag_retrieval()
    test_clinical_scenarios()
    test_performance()
    test_data_consistency()
    
    # Summary
    print("\n" + "="*60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f" RESULTS: {RESULTS['passed']}/{total} passed ({100*RESULTS['passed']//total if total else 0}%)")
    print("="*60)
    
    return RESULTS["failed"] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
