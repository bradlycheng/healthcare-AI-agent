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

    # ── 7a. Vector store basics ───────────────────────────────────────────────
    try:
        from app.vector_store import get_document_count, search

        doc_count = get_document_count()
        log_test("RAG", f"Vector store has documents ({doc_count})", doc_count > 0)

        results = search("glucose diabetes", top_k=3)
        has_results = (
            results
            and results.get("documents")
            and len(results["documents"][0]) > 0
        )
        log_test("RAG", "Vector search returns results", has_results)

    except ImportError:
        log_test("RAG", "Vector store module available", False, "ImportError")
    except Exception as e:
        log_test("RAG", "RAG system functional", False, str(e))

    # ── 7b. retrieve_context returns properly shaped sources ──────────────────
    try:
        from app.query_assistant import retrieve_context

        _, sources = retrieve_context("what blood glucose level is considered diabetic")

        log_test("RAG", "retrieve_context returns sources list", isinstance(sources, list))

        if sources:
            src = sources[0]
            has_title     = "title" in src
            has_snippet   = "snippet" in src or "full_snippet" in src
            has_relevance = "relevance" in src
            valid_score   = isinstance(src.get("relevance"), (int, float)) and 0 <= src["relevance"] <= 1

            log_test("RAG", "Source has 'title' field",           has_title,     str(src.get("title")))
            log_test("RAG", "Source has 'snippet' field",         has_snippet,   "")
            log_test("RAG", "Source has 'relevance' score 0-1",   valid_score,   str(src.get("relevance")))
        else:
            log_test("RAG", "retrieve_context returned >0 sources", False,
                     "0 sources returned - check if docs are indexed")

    except Exception as e:
        log_test("RAG", "retrieve_context source shape check", False, str(e))

    # ── 7c. /api/query response includes sources (requires server) ────────────
    import requests
    BASE_URL = "http://localhost:8080"
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        server_up = r.status_code == 200
    except Exception:
        server_up = False

    if not server_up:
        print("  [SKIP] RAG API tests skipped - server not running")
        print("  To test: run 'uvicorn app.api:app --port 8080' first")
        return

    CLINICAL_QUESTIONS = [
        "what blood glucose level is considered diabetic",
        "what is the normal blood pressure range",
    ]

    for i, question in enumerate(CLINICAL_QUESTIONS):
        if i > 0:
            import time; time.sleep(12)   # avoid LLM rate-limit between questions
        try:
            resp = requests.post(
                f"{BASE_URL}/api/query",
                json={"question": question, "history": [], "reasoning_depth": "standard"},
                timeout=60,
            )
            log_test("RAG API", f"POST /api/query 200 for '{question[:35]}...'",
                     resp.status_code == 200, f"status={resp.status_code}")

            if resp.status_code == 200:
                data = resp.json()

                # sources key must exist and be a list
                has_sources_key  = "sources" in data and isinstance(data["sources"], list)
                has_sources_data = has_sources_key and len(data["sources"]) > 0
                log_test("RAG API", f"Response has 'sources' array for '{question[:30]}...'",
                         has_sources_key, "")
                log_test("RAG API", f"sources array is non-empty for '{question[:30]}...'",
                         has_sources_data,
                         f"{len(data.get('sources', []))} source(s) returned")

                if has_sources_data:
                    src = data["sources"][0]
                    log_test("RAG API", "First source has 'title'",
                             bool(src.get("title")), str(src.get("title", "")))
                    log_test("RAG API", "First source has 'relevance' (0-1)",
                             isinstance(src.get("relevance"), (int, float)) and 0 <= src["relevance"] <= 1,
                             str(src.get("relevance", "")))

        except Exception as e:
            log_test("RAG API", f"Query '{question[:35]}...'", False, str(e))

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

# =============================================================================
# 8. AGENT RAG CHANGE REGRESSION TESTS
#    Verifies that the three healthcare_agent.py changes (direct_answer sources,
#    query_database sources, deduplication) do NOT corrupt other response types.
# =============================================================================
def test_agent_rag_regression():
    print_header("8. AGENT RAG CHANGE REGRESSION TESTS")

    import requests
    BASE_URL = "http://localhost:8080"

    try:
        server_up = requests.get(f"{BASE_URL}/health", timeout=5).status_code == 200
    except Exception:
        server_up = False

    if not server_up:
        print("  [SKIP] Regression tests skipped — server not running")
        print("  To run: uvicorn app.api:app --port 8080")
        return

    def query(question, history=None):
        """Helper: POST /api/query and return parsed JSON or None."""
        import time, requests as _req
        time.sleep(12)   # prevent LLM rate-limit across sequential test calls
        try:
            r = _req.post(
                f"{BASE_URL}/api/query",
                json={"question": question, "history": history or [], "reasoning_depth": "standard"},
                timeout=60,
            )
            return r.json() if r.status_code == 200 else None
        except Exception:
            return None

    # ── 8a. Patient data query: SQL answer still correct ─────────────────────
    # This exercises the query_database path — the new RAG call must NOT
    # alter the SQL result or overwrite the answer.
    print("\n  [8a] Patient data query — SQL answer unaffected by RAG change")
    data = query("how many patients are in the system?")
    if data is None:
        log_test("Regression", "Patient query returns 200", False, "request failed")
    else:
        log_test("Regression", "Patient query returns 200", True)
        # Answer should mention a number or 'patient'
        answer_lower = (data.get("answer") or "").lower()
        has_number_or_patient = any(c.isdigit() for c in answer_lower) or "patient" in answer_lower
        log_test("Regression", "Patient query answer is sensible (not empty/error)",
                 has_number_or_patient, repr(data.get("answer", "")[:80]))
        # answer must NOT be a RAG-style clinical answer
        looks_like_rag_bleed = any(kw in answer_lower for kw in
                                   ["blood glucose", "mmol", "clinical guideline"])
        log_test("Regression", "Patient SQL answer not polluted with RAG text",
                 not looks_like_rag_bleed, data.get("answer", "")[:80])
        # sources may be present (expected) but must be a list
        sources = data.get("sources", [])
        log_test("Regression", "sources field is a list", isinstance(sources, list))

    # ── 8b. Greeting / meta — answer unchanged, no spurious sources shown ────
    print("\n  [8b] Greeting query — response unaffected")
    data2 = query("hello, what can you help me with?")
    if data2 is None:
        log_test("Regression", "Greeting query returns 200", False, "request failed")
    else:
        log_test("Regression", "Greeting query returns 200", True)
        answer_lower2 = (data2.get("answer") or "").lower()
        # Must still give a helpful response
        is_helpful = len(answer_lower2) > 10
        log_test("Regression", "Greeting answer is non-empty", is_helpful,
                 repr(data2.get("answer", "")[:80]))
        # Any sources returned must be a list (even if empty for greetings)
        log_test("Regression", "Greeting sources field is a list",
                 isinstance(data2.get("sources", []), list))

    # ── 8c. Direct-answer path: answer intact, sources now populated ─────────
    # Knowledge questions often go through direct_answer — verify the answer
    # is still the LLM's knowledge answer, but sources are now attached.
    print("\n  [8c] Knowledge/direct-answer path — answer correct, sources added")
    data3 = query("what does BMI stand for?")
    if data3 is None:
        log_test("Regression", "Knowledge query returns 200", False, "request failed")
    else:
        log_test("Regression", "Knowledge query returns 200", True)
        answer_lower3 = (data3.get("answer") or "").lower()
        # Must contain 'body mass index' or 'bmi' in answer
        answer_correct = "body mass index" in answer_lower3 or "bmi" in answer_lower3
        log_test("Regression", "BMI answer contains correct definition",
                 answer_correct, repr(data3.get("answer", "")[:80]))
        # sources is always a list now
        log_test("Regression", "Knowledge query sources is a list",
                 isinstance(data3.get("sources", []), list))

    # ── 8d. No duplicate sources in any response ─────────────────────────────
    print("\n  [8d] Deduplication — no duplicate source titles in any response")
    data4 = query("what blood glucose level means diabetes according to guidelines?")
    if data4 is None:
        log_test("Regression", "Clinical query returns 200", False, "request failed")
    else:
        log_test("Regression", "Clinical query returns 200", True)
        sources4 = data4.get("sources", [])
        titles = [s.get("title", "") for s in sources4]
        has_duplicates = len(titles) != len(set(titles))
        log_test("Regression", f"No duplicate source titles ({len(titles)} source(s), titles: {titles})",
                 not has_duplicates, f"duplicates found: {[t for t in set(titles) if titles.count(t) > 1]}")

    # ── 8e. Specific patient query — sql_used reported, not empty ────────────
    print("\n  [8e] Specific patient lookup — sql_used still populated")
    data5 = query("show me patients with high blood pressure")
    if data5 is None:
        log_test("Regression", "Specific patient query returns 200", False, "request failed")
    else:
        log_test("Regression", "Specific patient query returns 200", True)
        sql = data5.get("sql_used", "")
        # When query_database is used, sql_used should be populated
        # (it won't be if the agent went direct_answer — that's also acceptable)
        tools_used = data5.get("tools_used", [])
        if "query_database" in tools_used:
            log_test("Regression", "sql_used populated when query_database called",
                     bool(sql), repr(sql[:80]))
        else:
            log_test("Regression", "Agent responded (any tool path)",
                     bool(data5.get("answer")), f"tools_used={tools_used}")

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
    test_agent_rag_regression()    # ← new section 8

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
