# Prompt Ledger

Entries are prepended (newest first).

---

## 2026-06-02 — Slice 6 Reviewer Pass (MERGEABLE)

Slice 6 (Database Connection & Storage Hardening) reviewed read-only. All five sign-off conditions verified: `patient_timeline.py` uses only `get_connection()` (AST-confirmed, `import sqlite3` removed); `BEGIN IMMEDIATE` wraps count+INSERT with rollback on cap; patient fields truncated with `logger.warning()` reporting length only; `deletion_audit` rows written before all cascading DELETEs; table in `init_db()` schema. 17/17 tests pass including a real two-thread race test. 1 pre-existing async failure in `test_context_memory` confirmed unrelated. Verdict: **MERGEABLE**.

---

## 2026-06-02 — Slice 6 Worker: DB & Timeline Hardening

**Session type:** Narrow-worker — Slice 6 execution
**Files modified:** `app/patient_timeline.py`, `app/db.py`
**Artifacts written:** `tests/test_slice6_db_hardening.py`, `docs/agent-reports/baseline-audit/60-slice6-worker.md`

**Summary:** Implemented final DB hardening slice. In `app/patient_timeline.py`, removed both `sqlite3.connect()` calls (in `get_unique_patients()` and `get_patient_timeline()`) and replaced them with `get_connection()` imported from `app.db`, ensuring WAL mode and 5000 ms busy timeout apply uniformly. In `app/db.py`, added a module-level `logger`, created the `deletion_audit` table in `init_db()` (columns: `id`, `message_id`, `patient_id`, `deleted_at`), enforced patient field max-lengths (`first_name`/`last_name` ≤ 100, `patient_id` ≤ 50, `dob` ≤ 10) with silent truncation and `logger.warning()` on each truncation, wrapped the storage-limit count-check and INSERT in `BEGIN IMMEDIATE` to eliminate the TOCTOU race, and inserted `deletion_audit` rows (with timestamp) before every `DELETE FROM hl7_messages` in both `prune_messages()` and `delete_all_messages()`. 17/17 new tests pass; 163/164 overall (1 pre-existing async failure in `test_context_memory` unrelated to this slice).

---

## 2026-06-02 — Slice 5 Reviewer Pass (MERGEABLE)

Slice 5 (API Rate Limiting & CORS Hardening) reviewed read-only. All four sign-off conditions verified: CORS never `"*"`, XFF only trusted via `TRUSTED_PROXIES`, admin 503 when password unset, delay 3.0s. 15/15 tests pass with wall-clock delay check and TestClient 503 path. Scope clean (only `app/api.py`). Non-blocking: exponential backoff not added (acceptable); startup warning instead of hard fail (acceptable per demo mode). Verdict: **MERGEABLE**.

---

## 2026-06-02 — Slice 5 Worker: API Hardening

**Session type:** Narrow-worker — Slice 5 execution
**Files modified:** `app/api.py`
**Artifacts written:** `tests/test_slice5_api_hardening.py`, `docs/agent-reports/baseline-audit/50-slice5-worker.md`

**Summary:** Implemented four API hardening items in `app/api.py`. (1) CORS wildcard replaced: `allow_origins=["*"]` removed; `ALLOWED_ORIGINS` is now read from the env var of the same name (comma-separated), defaulting to `["http://localhost:8000","http://localhost:8080"]` when unset or empty — the literal `"*"` can never appear. (2) Rate-limit X-Forwarded-For validation added: new `_get_rate_limit_key()` helper reads `TRUSTED_PROXIES` env var; only uses the first XFF address when `request.client.host` appears in that list, otherwise always falls back to `request.client.host`; all three rate-limit call sites updated. (3) Admin password hardcoded default removed: `ADMIN_PASSWORD` is now read at module level with no fallback; startup emits `logger.warning()` when unset; `/admin/reset` returns HTTP 503 with message "Admin endpoint unavailable: server not configured" when the variable is missing. (4) Admin brute-force delay raised from 1.0 s to 3.0 s. 15/15 new tests pass; 19/19 regression tests (api/cors/admin/rate scope) pass, 0 regressions.

---

## 2026-06-02 — Slice 4 Reviewer Pass (MERGEABLE)

Slice 4 (HL7 Input Boundary Enforcement) reviewed read-only. All five sign-off conditions verified: OBX count cap at 500 with warning+ValueError; NM type mismatch skips with warning; missing PID raises ValueError; `hl7_ts_to_iso()` range-validates all date fields; API returns 400 for missing PID/OBX. 30/30 tests pass with substantive assertions including caplog, boundary tests at 500/501, and API detail-field checks. Scope clean. Verdict: **MERGEABLE**.

---

## 2026-06-02 — Slice 4 Worker: HL7 Boundary & Structural Validation

**Session type:** Narrow-worker — Slice 4 execution
**Files modified:** `app/hl7_parser.py`, `app/fhir_builder.py`, `app/api.py`
**Artifacts written:** `tests/test_slice4_hl7_boundary.py`, `docs/agent-reports/baseline-audit/40-slice4-worker.md`

**Summary:** Implemented HL7 boundary and structural hardening for Slice 4. In `app/hl7_parser.py`, added `_MAX_OBX_COUNT = 500` constant and a pre-loop OBX count guard in `_parse_observations()` that calls `logger.warning()` and raises `ValueError` when the count exceeds 500; added an NM value-type mismatch guard that calls `logger.warning()` and `continue`s (skipping the observation) when OBX-2 is `NM` but the value string cannot be cast to `float`; replaced the silent `return patient` fallback in `_parse_patient()` with `raise ValueError("...missing required PID segment.")` for absent PID and a second `raise ValueError("...missing patient ID (PID-3).")` for a PID with an empty identifier. In `app/fhir_builder.py`, added range-validation logic inside `hl7_ts_to_iso()` for both 14-char and 8-char branches — month 01-12, day 01-31, hour 00-23, minute 00-59 are checked with `int()` conversion and raise `ValueError` with a descriptive message on violation. In `app/api.py`, added two `HTTPException(status_code=400)` guards in the `/oru/parse` handler after the existing MSH check, rejecting messages missing `PID|` or `OBX|` before any parsing occurs. 30 new tests written and passing; 0 regressions (55/55 hl7/parse/fhir-scoped tests pass).

---

## 2026-06-02 — Slice 3 Reviewer Pass (MERGEABLE)

Slice 3 (LLM Output Validation) reviewed against the baseline hardening plan and worker report 30-slice3-worker.md. All sign-off conditions verified: `_validate_ai_observation()` enforces LOINC regex, rejects booleans/None/empty strings/strings>=200 chars/non-finite floats with `logger.warning()`; `_merge_llm_output()` caps at 10 with truncation warning; AI pipeline `except` replaced with `logger.error()`; `_try_repair_json()` logs repair with no raw content. 32/32 tests pass including an AST-walk guard against bare-`pass` excepts and a PII-leak assertion on the repair warning. Only `app/agent.py` and `app/llm_client.py` touched. Verdict: **MERGEABLE**.

---

## 2026-06-02 — Slice 3 Worker: LLM Output Validation

**Session type:** Narrow-worker — Slice 3 execution
**Files modified:** `app/agent.py`, `app/llm_client.py`
**Artifacts written:** `tests/test_slice3_llm_output_validation.py`, `docs/agent-reports/baseline-audit/30-slice3-worker.md`

**Summary:** Implemented LLM output validation hardening for Slice 3. In `app/agent.py`, added compile-time `_LOINC_RE = re.compile(r"^\d{4,6}-\d$")` and `_MAX_AI_OBS = 10` constants, introduced a `_validate_ai_observation()` helper that rejects observations with non-LOINC codes or invalid values (None, empty string, strings >= 200 chars, non-finite floats) — each rejection emits a `logger.warning()` with the reason and code but no patient data; refactored `_merge_llm_output()` to apply the count cap (with a truncation warning when >10 observations are returned) and route all observations through `_validate_ai_observation()` before merge; replaced the `print()`/`traceback.print_exc()`/`pass` in the AI pipeline except block with a single `logger.error()` carrying only the exception type and message. In `app/llm_client.py`, added a `logger` instance, replaced the Bedrock-init `print()` with `logger.warning()`, and added a `logger.warning()` in `_try_repair_json()` that fires when a missing-closing-brace repair is attempted — the warning contains no raw JSON content. 32 new tests written and passing; 0 regressions.

---

## 2026-06-02 — Slice 2 Reviewer Pass (MERGEABLE)

Slice 2 (LLM Prompt Injection Defense) reviewed against the baseline hardening plan and worker report 20-slice2-worker.md. All sign-off conditions verified: NTE-3 clinical notes re-sanitized via `sanitize_text()` in `app/agent.py:126`; patient name, obs display, and note text wrapped in `[PATIENT_DATA]...[/PATIENT_DATA]` in both `agent.py` and `patient_timeline.py`; all 6 required injection patterns added to `security.py` with `(?i)` flags; bare `print()` in `patient_timeline.py` replaced with `logging.warning()`. 24/24 tests pass with substantive assertions. Scope clean. Non-blocking follow-up: migrate `agent.py:261` `print()` to `logging.error()`. Verdict: **MERGEABLE**.

---

## 2026-06-02 — Slice 2 Worker: Prompt Injection Hardening

**Session type:** Narrow-worker — Slice 2 execution
**Files modified:** `app/agent.py`, `app/patient_timeline.py`, `app/security.py`
**Artifacts written:** `tests/test_slice2_prompt_injection.py`, `docs/agent-reports/baseline-audit/20-slice2-worker.md`

**Summary:** Implemented prompt injection hardening for Slice 2. In `app/security.py`, expanded `INJECTION_PATTERNS` with 5 new multi-word patterns (`you've become`, `you have become`, `act as if`, `pretend you are`, `pretend to be`) and updated the `System:` / `Human:` patterns to use `\s*:` so that `SYSTEM :` and `HUMAN :` (with a space before the colon) are now also caught — all patterns are case-insensitive via `(?i)`. In `app/agent.py`, re-sanitized each NTE-3 note string individually via `sanitize_text()` immediately after extraction in `_build_llm_prompt()`, closing the bypass gap; also wrapped observation display labels and note text in `[PATIENT_DATA]...[/PATIENT_DATA]` delimiter tags. In `app/patient_timeline.py`, wrapped patient first+last name and observation display/value text in `[PATIENT_DATA]...[/PATIENT_DATA]` tags in the journey-summary prompt, and replaced a bare `print(f"Journey summary error: {e}")` (which could leak exception context) with `logging.warning(..., type(e).__name__)`. 24 new tests written and passing; 0 regressions.

---

## 2026-06-02 — Slice 1 review (SQL Injection Prevention)

security-reviewer read-only pass over `app/db.py`, `app/query_assistant.py`, and the new `tests/test_slice1_sql_hardening.py`. Confirmed `prune_messages()` is fully parameterized (no f-string SQL), `validate_sql()` is case-insensitive via a single `.upper().strip()` normalization, the 1000-row cap is enforced through `fetchmany(QUERY_ROW_CAP)`, all required forbidden keywords (PRAGMA, ATTACH, DETACH, VACUUM, ANALYZE, EXPLAIN, UNION, CROSS JOIN) are present, and the read-only connection failure now logs a warning instead of silently falling through. Scope discipline verified by `git status` — only the two owned files plus the new test file changed. All 45 tests pass. Verdict: MERGEABLE. Two cosmetic non-blocking notes filed in `11-slice1-reviewer.md`.

---

## 2026-06-02 — Slice 1 Worker: SQL Injection Prevention

**Session type:** Narrow-worker — Slice 1 execution  
**Files modified:** `app/db.py`, `app/query_assistant.py`  
**Artifacts written:** `tests/test_slice1_sql_hardening.py`, `docs/agent-reports/baseline-audit/10-slice1-worker.md`

**Summary:** Implemented SQL hardening for Slice 1. In `app/db.py`, removed f-string SQL from `prune_messages()` (the two DELETE statements now use string concatenation to build the query template, with IDs still bound as parameterized tuples). In `app/query_assistant.py`, confirmed the previously-added hardening was complete (FORBIDDEN_KEYWORDS includes PRAGMA/ATTACH/DETACH/VACUUM/ANALYZE/EXPLAIN/UNION/CROSS JOIN; validate_sql() normalizes to uppercase before all checks; execute_safe_query() uses fetchmany(1000) row cap); added a `logger.warning()` when the read-only SQLite connection fails so the failure is never silent. 45 new tests written and passing; 0 regressions.

---

## 2026-06-02 — Baseline Security Audit (Lead Session)

**Session type:** Lead — baseline audit  
**Agents dispatched:** security-explorer, hl7-storage-explorer (parallel)  
**Artifacts written:** `docs/agent-reports/baseline-audit/00-lead-hardening-plan.md`, `docs/agent-reports/prompt-ledger.md`

**Summary:** Ran parallel baseline security audit across the full security kernel (warden, guards, intent classifier, grant builder, token guard, llm_gateway, api) and the HL7 ingestion/storage surface (hl7_parser, fhir_builder, agent, db, api). Both explorers returned findings independently. Lead synthesized into 6 prioritized hardening slices. Critical findings: SQL injection pattern in `db.prune_messages()` via f-string interpolation; unescaped NTE-3 clinical notes reaching LLM prompt without re-sanitization; LLM output merged into DB with only null checks (no LOINC format validation, no count cap). High findings: unbounded OBX segment count (DoS vector), CORS wildcard, rate limiter bypassable via X-Forwarded-For spoofing, weak admin password default. 6 slices defined with narrow file ownership, sign-off conditions, and test names. Authentication deferred (intentional demo mode). Raw HL7 encryption deferred (requires dependency change). Plan is ready for `/run-hardening-slice`.
