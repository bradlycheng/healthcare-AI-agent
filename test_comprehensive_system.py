"""
COMPREHENSIVE SYSTEM TEST SUITE
Tests all major components of the Healthcare AI Agent
"""
import sqlite3
import os
import json
import sys
from datetime import datetime

# Test results tracking
RESULTS = {"passed": 0, "failed": 0, "tests": []}

def log_test(category, name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    RESULTS["passed" if passed else "failed"] += 1
    RESULTS["tests"].append({"category": category, "name": name, "status": status, "details": details})
    symbol = "[OK]" if passed else "[FAIL]"
    print(f"  {symbol} {name}" + (f" - {details}" if details and not passed else ""))

def print_header(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

# =============================================================================
# 1. DATABASE SCHEMA TESTS
# =============================================================================
def test_database_schema():
    print_header("1. DATABASE SCHEMA TESTS")
    
    DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Test table existence
    tables = ["hl7_messages", "observations", "medications", "diagnoses", "visits"]
    for table in tables:
        try:
            cursor.execute(f"SELECT 1 FROM {table} LIMIT 1")
            log_test("Schema", f"Table '{table}' exists", True)
        except sqlite3.OperationalError as e:
            log_test("Schema", f"Table '{table}' exists", False, str(e))
    
    # Test loinc_code column in observations
    try:
        cursor.execute("SELECT loinc_code FROM observations LIMIT 1")
        log_test("Schema", "observations.loinc_code column exists", True)
    except sqlite3.OperationalError as e:
        log_test("Schema", "observations.loinc_code column exists", False, str(e))
    
    # Test foreign key relationship
    try:
        cursor.execute("""
            SELECT o.id FROM observations o 
            JOIN hl7_messages h ON o.message_id = h.id 
            LIMIT 1
        """)
        log_test("Schema", "observations -> hl7_messages FK works", True)
    except Exception as e:
        log_test("Schema", "observations -> hl7_messages FK works", False, str(e))
    
    conn.close()

# =============================================================================
# 2. DATA INTEGRITY TESTS
# =============================================================================
def test_data_integrity():
    print_header("2. DATA INTEGRITY TESTS")
    
    DB_PATH = os.getenv("DATABASE_PATH", "agent.db")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Test patient count
    count = cursor.execute("SELECT COUNT(DISTINCT patient_id) FROM hl7_messages").fetchone()[0]
    log_test("Data", f"Patients exist ({count} found)", count > 0, f"Expected >0, got {count}")
    
    # Test observations count
    obs_count = cursor.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    log_test("Data", f"Observations exist ({obs_count} found)", obs_count > 0)
    
    # Test medications count
    med_count = cursor.execute("SELECT COUNT(*) FROM medications").fetchone()[0]
    log_test("Data", f"Medications exist ({med_count} found)", med_count > 0)
    
    # Test diagnoses count
    diag_count = cursor.execute("SELECT COUNT(*) FROM diagnoses").fetchone()[0]
    log_test("Data", f"Diagnoses exist ({diag_count} found)", diag_count > 0)
    
    # Test visits count
    visit_count = cursor.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    log_test("Data", f"Visits exist ({visit_count} found)", visit_count > 0)
    
    # Test observation flags are valid
    invalid_flags = cursor.execute("""
        SELECT COUNT(*) FROM observations 
        WHERE flag NOT IN ('H', 'L', 'N', 'HH', 'LL', '') AND flag IS NOT NULL
    """).fetchone()[0]
    log_test("Data", "Observation flags are valid (H/L/N)", invalid_flags == 0, f"{invalid_flags} invalid")
    
    # Test medications have valid status
    invalid_status = cursor.execute("""
        SELECT COUNT(*) FROM medications 
        WHERE status NOT IN ('Active', 'Discontinued', 'Completed') AND status IS NOT NULL
    """).fetchone()[0]
    log_test("Data", "Medication statuses are valid", invalid_status == 0)
    
    conn.close()

# =============================================================================
# 3. AI QUERY ASSISTANT TESTS
# =============================================================================
def test_ai_query_assistant():
    print_header("3. AI QUERY ASSISTANT TESTS")
    
    from app.query_assistant import process_query, validate_sql
    
    # Test SQL validation - should block dangerous queries
    dangerous_queries = [
        ("DELETE FROM hl7_messages", "DELETE blocked"),
        ("DROP TABLE observations", "DROP blocked"),
        ("INSERT INTO medications VALUES (1,2,3)", "INSERT blocked"),
        ("UPDATE hl7_messages SET patient_id='hack'", "UPDATE blocked"),
    ]
    
    for sql, test_name in dangerous_queries:
        is_valid, _ = validate_sql(sql)
        log_test("Security", test_name, not is_valid)
    
    # Test SELECT is allowed
    is_valid, _ = validate_sql("SELECT * FROM hl7_messages LIMIT 1")
    log_test("Security", "SELECT allowed", is_valid)
    
    # Test natural language queries
    test_queries = [
        ("How many patients?", lambda r: r["row_count"] >= 1),
        ("Show all patients", lambda r: r["row_count"] >= 1),
        ("Who has diabetes?", lambda r: r["success"]),
        ("Who is taking Metformin?", lambda r: r["success"]),
        ("Show patients with high glucose", lambda r: r["success"]),
    ]
    
    for question, validator in test_queries:
        try:
            result = process_query(question)
            passed = result["success"] and validator(result)
            log_test("AI Query", f"'{question[:30]}...'", passed, 
                    f"rows={result.get('row_count', 0)}" if passed else result.get("error", ""))
        except Exception as e:
            log_test("AI Query", f"'{question[:30]}...'", False, str(e))

# =============================================================================
# 4. API ENDPOINT TESTS
# =============================================================================
def test_api_endpoints():
    print_header("4. API ENDPOINT TESTS")
    
    import requests
    
    BASE_URL = "http://localhost:8080"
    
    # Check if server is running
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        server_up = r.status_code == 200
    except:
        server_up = False
    
    if not server_up:
        print("  [SKIP] API server not running - skipping endpoint tests")
        print("  To test: run 'uvicorn app.api:app --port 8080' first")
        return
    
    # Test endpoints
    endpoints = [
        ("GET", "/health", 200),
        ("GET", "/messages", 200),
        ("GET", "/patients", 200),
    ]
    
    for method, path, expected_status in endpoints:
        try:
            if method == "GET":
                r = requests.get(f"{BASE_URL}{path}", timeout=10)
            passed = r.status_code == expected_status
            log_test("API", f"{method} {path}", passed, f"status={r.status_code}")
        except Exception as e:
            log_test("API", f"{method} {path}", False, str(e))

# =============================================================================
# 5. EDGE CASE TESTS
# =============================================================================
def test_edge_cases():
    print_header("5. EDGE CASE TESTS")
    
    from app.query_assistant import process_query
    
    edge_cases = [
        # Empty/invalid queries
        ("", "Empty query handled"),
        ("   ", "Whitespace query handled"),
        ("asdfghjkl", "Gibberish query handled"),
        
        # Potential injection attempts
        ("'; DROP TABLE users; --", "SQL injection attempt 1"),
        ("1=1; SELECT * FROM passwords", "SQL injection attempt 2"),
        
        # Very long query
        ("Show me " + "all " * 100 + "patients", "Long query handled"),
        
        # Unicode
        ("Show patients named José García", "Unicode in query handled"),
    ]
    
    for query, test_name in edge_cases:
        try:
            result = process_query(query)
            # Edge cases should either succeed gracefully or fail safely (no exceptions)
            log_test("Edge Case", test_name, True)
        except Exception as e:
            log_test("Edge Case", test_name, False, f"Exception: {str(e)[:50]}")

# =============================================================================
# 6. PRONOUN RESOLUTION TESTS
# =============================================================================
def test_pronoun_resolution():
    print_header("6. PRONOUN/CONTEXT TESTS")
    
    from app.query_assistant import process_query
    
    # Test with explicit history
    history = [
        {"role": "user", "content": "Show me Sarah Johnson's results"},
        {"role": "assistant", "content": "Sarah Johnson (10001) has the following results: Glucose 156 mg/dL (High)..."}
    ]
    
    # Follow-up should use context
    result = process_query("What medications is she taking?", history)
    
    # Check if the query included Sarah or 10001
    sql_lower = result.get("sql_used", "").lower()
    has_context = "sarah" in sql_lower or "10001" in sql_lower or "johnson" in sql_lower
    log_test("Context", "Pronoun 'she' resolved from history", has_context, 
             f"SQL: {result.get('sql_used', '')[:80]}...")
    
    # Test without history - should not filter by patient
    result2 = process_query("What about his glucose?", [])  # No history
    # This should either fail gracefully or not filter by a specific patient
    log_test("Context", "No history - handled gracefully", result2["success"] or "error" not in result2)

# =============================================================================
# 7. RAG/VECTOR STORE TESTS
# =============================================================================
def test_rag_integration():
    print_header("7. RAG INTEGRATION TESTS")
    
    try:
        from app.vector_store import get_document_count, search
        
        doc_count = get_document_count()
        log_test("RAG", f"Vector store has documents ({doc_count})", doc_count > 0)
        
        # Test search
        results = search("glucose diabetes", top_k=3)
        has_results = results and results.get("documents") and len(results["documents"][0]) > 0
        log_test("RAG", "Search returns results", has_results)
        
    except ImportError:
        log_test("RAG", "Vector store module available", False, "ImportError")
    except Exception as e:
        log_test("RAG", "RAG system functional", False, str(e))

# =============================================================================
# MAIN
# =============================================================================
def main():
    print("\n" + "="*60)
    print(" HEALTHCARE AI AGENT - COMPREHENSIVE TEST SUITE")
    print(" " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)
    
    # Run all test categories
    test_database_schema()
    test_data_integrity()
    test_ai_query_assistant()
    test_api_endpoints()
    test_edge_cases()
    test_pronoun_resolution()
    test_rag_integration()
    
    # Summary
    print("\n" + "="*60)
    print(" TEST SUMMARY")
    print("="*60)
    total = RESULTS["passed"] + RESULTS["failed"]
    print(f" Total Tests: {total}")
    print(f" Passed:      {RESULTS['passed']} ({100*RESULTS['passed']//total if total else 0}%)")
    print(f" Failed:      {RESULTS['failed']}")
    print("="*60)
    
    # List failures
    failures = [t for t in RESULTS["tests"] if t["status"] == "FAIL"]
    if failures:
        print("\n FAILED TESTS:")
        for f in failures:
            print(f"   - [{f['category']}] {f['name']}: {f['details']}")
    
    return RESULTS["failed"] == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
