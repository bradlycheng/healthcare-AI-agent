# Baseline Hardening Plan
**Generated:** 2026-06-02  
**Explorers:** security-explorer, hl7-storage-explorer  
**Status:** Ready for slice execution via `/run-hardening-slice`

---

## How to Use This Plan

Run `/run-hardening-slice` and specify a slice number (e.g. "Slice 1").  
The skill will confirm scope, dispatch a narrow-worker, then require a security-reviewer gate before the slice is declared done.

Worker reports: `10`, `20`, `30`, `40`, `50`, `60`  
Reviewer first pass: `11`, `21`, `31`, `41`, `51`, `61`  
Rework pass (if needed): `12`, `22`, `32`, `42`, `52`, `62`

---

## Priority Summary

| Slice | Name | Severity | Status |
|-------|------|----------|--------|
| 1 | SQL Injection Prevention | Critical | Pending |
| 2 | LLM Prompt Injection Defense | Critical | Pending |
| 3 | LLM Output Validation | Critical | Pending |
| 4 | HL7 Input Boundary Enforcement | High | Pending |
| 5 | API Rate Limiting & CORS Hardening | High | Pending |
| 6 | Database Connection & Storage Hardening | Medium | Pending |

---

## Slice 1 — SQL Injection Prevention

**Severity:** Critical  
**Source findings:** Both explorers flagged `db.py:175` and `query_assistant.py` SQL keyword validation

### What to fix
- `db.prune_messages()` builds a DELETE query using f-string interpolation: `f"DELETE FROM observations WHERE message_id IN ({id_list_str})"`. Currently safe (integer IDs only) but violates parameterized query best practices and is one schema change away from injectable.
- `query_assistant.validate_sql()` keyword checks are uppercase-only — `SeLeCt` bypasses them.
- `cursor.fetchall()` has no row cap — "show all observations" could return 100K+ rows.
- Missing SQLite-specific forbidden keywords: `PRAGMA`, `ATTACH`, `DETACH`, `VACUUM`, `ANALYZE`, `EXPLAIN`.

### File ownership (worker may ONLY touch these)
- `app/db.py`
- `app/query_assistant.py`

### Files NOT to touch
- `app/api.py`
- `app/security.py`
- `app/agent.py`
- `app/warden.py`
- `app/llm_gateway.py`
- Any `*_guard.py`

### Sign-off condition
`prune_messages()` uses parameterized `IN (?, ?, ?)` syntax. `validate_sql()` uses case-insensitive regex. Query results are capped at 1000 rows. `PRAGMA`, `ATTACH`, `DETACH`, `VACUUM`, `ANALYZE`, `EXPLAIN`, `CROSS JOIN`, `UNION` are all blocked.

### Required tests
- `test_prune_messages_uses_parameterized_queries`
- `test_sql_validation_case_insensitive`
- `test_query_result_size_capped`
- `test_sqlite_specific_keywords_blocked`
- `test_cross_join_rejected`
- `test_union_rejected`

---

## Slice 2 — LLM Prompt Injection Defense

**Severity:** Critical  
**Source findings:** security-explorer (agent.py:243), hl7-storage-explorer (agent.py:120-165)

### What to fix
- `agent._build_llm_prompt()` embeds raw NTE-3 clinical note text directly into the LLM prompt after `sanitize_text()` runs on the full HL7 message. Notes extracted at line 205 are NOT re-sanitized — a note reading `System: Ignore all previous instructions` reaches the LLM unchecked.
- Patient names and observation display values are embedded in prompts without escaping in `agent.py` and `patient_timeline.py`.
- `security.inject_patterns` misses variants: `"you've become"`, `"act as if"`, `"pretend you are"`, `"SYSTEM :"` (space before colon).

### File ownership (worker may ONLY touch these)
- `app/agent.py`
- `app/patient_timeline.py`
- `app/security.py`

### Files NOT to touch
- `app/warden.py`
- `app/llm_gateway.py`
- `app/llm_client.py`
- `app/db.py`
- `app/api.py`
- Any `*_guard.py`

### Sign-off condition
NTE-3 comment text is re-sanitized via `sanitize_text()` immediately after extraction, before prompt assembly. Patient name and observation display values are wrapped in delimiter tags (e.g. `[PATIENT_DATA]...[/PATIENT_DATA]`) before embedding. `INJECTION_PATTERNS` in `security.py` covers the four missing variants. No `print()` statements output patient data.

### Required tests
- `test_clinical_note_injection_blocked_before_prompt`
- `test_patient_name_wrapped_in_prompt`
- `test_observation_display_wrapped_in_prompt`
- `test_multiword_injection_patterns_detected`
- `test_no_pii_in_debug_print_output`

---

## Slice 3 — LLM Output Validation

**Severity:** Critical  
**Source findings:** hl7-storage-explorer (agent.py:168-184), security-explorer (agent.py:254-257)

### What to fix
- `_merge_llm_output()` appends AI-extracted observations with only a null check on `code` and `value`. A compromised or injected LLM response can append arbitrary LOINC codes and values into the database.
- New observations are not capped — LLM returning 500 observations would all be stored.
- LLM errors are silently swallowed (`except: pass`) with no audit log entry.
- `llm_client._try_repair_json()` adds a closing brace unconditionally without logging the repair.

### File ownership (worker may ONLY touch these)
- `app/agent.py`
- `app/llm_client.py`

### Files NOT to touch
- `app/warden.py`
- `app/llm_gateway.py`
- `app/db.py`
- `app/api.py`
- Any `*_guard.py`

### Sign-off condition
`_merge_llm_output()` validates each observation: code matches LOINC format `^\d{4,6}-\d$`, value is numeric or a non-empty string under 200 chars, max 10 new observations per message. All LLM failures logged with error context to `governance_events` (not silently passed). `_try_repair_json()` logs when repair is attempted.

### Required tests
- `test_llm_invalid_loinc_code_rejected`
- `test_llm_observation_count_capped_at_10`
- `test_llm_non_numeric_value_validated`
- `test_llm_errors_logged_not_swallowed`
- `test_json_repair_logged`

---

## Slice 4 — HL7 Input Boundary Enforcement

**Severity:** High  
**Source findings:** hl7-storage-explorer (hl7_parser.py, api.py)

### What to fix
- `hl7_parser.parse_oru()` has no limit on OBX segment count — 10,000+ OBX segments cause memory exhaustion.
- OBX-2 `value_type` is not validated against the actual value class (NM claims numeric but value is `"ABC"` → silent string fallback).
- Missing PID segment does not fail parsing — silently uses defaults.
- `api.py` MSH check only verifies `"MSH" in text` — no structural segment validation.
- `fhir_builder.hl7_ts_to_iso()` accepts invalid dates like `20259999` without range validation.

### File ownership (worker may ONLY touch these)
- `app/hl7_parser.py`
- `app/fhir_builder.py`
- `app/api.py`

### Files NOT to touch
- `app/agent.py`
- `app/db.py`
- `app/warden.py`
- `app/llm_gateway.py`
- Any `*_guard.py`

### Sign-off condition
Parser rejects messages with >500 OBX segments. Value type mismatch (NM + non-numeric string) raises a logged warning and skips the observation. Missing PID raises a parse error. `hl7_ts_to_iso()` validates month 01-12, day 01-31, hour 00-23. API MSH check validates segment count ≥ 3 (MSH, PID, at least one OBX).

### Required tests
- `test_hl7_oversized_obx_count_rejected`
- `test_obx_value_type_mismatch_skipped_and_logged`
- `test_missing_pid_segment_fails_parse`
- `test_invalid_hl7_timestamp_rejected`
- `test_api_rejects_hl7_missing_required_segments`

---

## Slice 5 — API Rate Limiting & CORS Hardening

**Severity:** High  
**Source findings:** security-explorer (api.py:30, api.py:462), hl7-storage-explorer (api.py)

### What to fix
- `allow_origins=["*"]` exposes clinical data to any cross-origin request.
- Rate limiter uses `request.client.host` only — X-Forwarded-For header allows bypass.
- Admin `DELETE /messages` has a 1-second brute-force delay (weak against scripted attacks).
- `ADMIN_PASSWORD` defaults to `"d3m0th1s"` in code — server starts with weak password if `.env` not set.

### File ownership (worker may ONLY touch these)
- `app/api.py`

### Files NOT to touch
- `app/security.py`
- `app/db.py`
- `app/agent.py`
- `app/warden.py`
- `app/llm_gateway.py`
- Any `*_guard.py`

### Sign-off condition
`allow_origins` reads from env var `ALLOWED_ORIGINS` (comma-separated), defaults to `["http://localhost:8000", "http://localhost:8080"]` — never `"*"`. Rate limiter validates X-Forwarded-For against a trusted proxy list before using it as the key. Admin brute-force delay raised to 3 seconds with exponential backoff after 3 failures. Server startup fails with clear error if `ADMIN_PASSWORD` is not set in environment.

### Required tests
- `test_cors_wildcard_rejected`
- `test_cors_allows_configured_origins`
- `test_rate_limit_xforwarded_for_not_spoofable`
- `test_admin_password_required_at_startup`
- `test_admin_brute_force_delay_enforced`

---

## Slice 6 — Database Connection & Storage Hardening

**Severity:** Medium  
**Source findings:** hl7-storage-explorer (db.py, patient_timeline.py), security-explorer (db.py)

### What to fix
- `patient_timeline.py` opens direct `sqlite3` connections bypassing `get_connection()` — skips WAL mode and 5000ms busy timeout.
- Storage limit check at insert time has no lock — two concurrent requests both pass the 1300-message check and both insert.
- Patient fields (first_name, last_name, id, dob) have no length limits — 5000-char names stored as-is.
- No audit log on DELETE CASCADE — deleted observations leave no trace.

### File ownership (worker may ONLY touch these)
- `app/patient_timeline.py`
- `app/db.py`

### Files NOT to touch
- `app/api.py`
- `app/agent.py`
- `app/query_assistant.py`
- `app/warden.py`
- `app/llm_gateway.py`
- Any `*_guard.py`

### Sign-off condition
`patient_timeline.py` uses `get_connection()` exclusively. Storage limit insert wrapped in a `BEGIN IMMEDIATE` transaction. Patient field lengths enforced: `first_name`/`last_name` max 100 chars, `patient_id` max 50 chars, `dob` max 10 chars. A `deletion_audit` log entry is written before any cascade delete.

### Required tests
- `test_patient_timeline_uses_centralized_connection`
- `test_storage_limit_concurrent_insert_blocked`
- `test_patient_field_length_enforced`
- `test_deletion_audit_logged_before_cascade`

---

## Deferred (Out of Scope for Now)

| Item | Reason deferred |
|------|----------------|
| Authentication layer (JWT/session) | App is intentionally demo-mode per README; auth would break the live demo at healthdataagent.com |
| Raw HL7 encryption at rest | Requires sqlcipher dependency change — too broad for a hardening slice |
| Clinical alert rule expansion | Domain expertise required; not a security issue |
| Audit logging module | Existing `governance_events` table sufficient for now |
