# Agent Report: hl7-storage-explorer

## Assignment
Baseline audit -- /oru/parse, /messages, parse sessions, FHIR/raw HL7 exposure, DB persistence, MLLP, client-trusted fields.

---

## Files Inspected

- app/hl7_parser.py -- ORU parsing, field extraction
- app/hl7_msh.py -- MSH segment parsing, ACK generation
- app/fhir_builder.py -- FHIR resource construction
- app/db.py -- SQLite schema, persistence, parse session lifecycle
- app/api.py -- HTTP endpoints, parse/save/list/detail routes
- app/agent.py -- ORU pipeline orchestration, FHIR building, LLM enrichment
- app/mllp_server.py -- MLLP socket handler
- app/alerts.py -- Clinical alert thresholds
- app/hl7_guard.py -- Input validation and bounds checking
- data/samples/sample_oru_1.hl7 -- Sample ORU message

---

## Current Flow

### Raw HL7 Input -> Parse -> FHIR -> DB -> API Response

1. **MLLP Ingestion** (`mllp_server.py:_recv_mllp_message`)
   - Socket reads MLLP framing (VT...FS+CR)
   - Decodes UTF-8 with `errors="replace"` -- lossy on bad bytes, silently corrupts
   - Passes to `process_mllp_hl7()` -> `run_oru_pipeline()`

2. **API Ingestion** (`api.py:parse_oru_endpoint`)
   - POST /oru/parse accepts raw HL7 in request body
   - Sanitizes via `sanitize_text(strict_ascii=True)` -- strips emojis, non-ASCII
   - Validates via `hl7_guard.validate_hl7_message()` -- structural checks only, not content
   - Calls `run_oru_pipeline(hl7_text, use_llm, persist)`

3. **HL7 Parsing** (`hl7_parser.py:parse_oru`)
   - `_normalize_hl7_text()` -- normalizes line endings
   - `parse_message()` -- uses hl7apy library
   - `_parse_patient()` -- extracts PID fields
   - `_parse_observations()` -- extracts OBX fields
   - **No validation of extracted field content** -- trusts HL7 input directly

4. **FHIR Construction** (`fhir_builder.py`, `agent.py`)
   - Simple pass-through wrapping of parsed dict into FHIR JSON
   - No deduplication, normalization, or code validation

5. **LLM Enrichment** (`agent.py:run_oru_pipeline`)
   - If observation contains text fields (TX, FT, ST, ED), calls `hl7_note_extraction()`
   - LLM-extracted observations merged with `source="AI_EXTRACTED"`
   - **No Warden scope around this LLM call** (see security-explorer finding C3)

6. **Alert Checking** (`agent.py`, `alerts.py`)
   - Calls `check_alert(code, value)` for each observation
   - Hardcoded LOINC rules (Troponin, Glucose, Potassium only)
   - **Alert triggered by code match alone -- no code validation**

7. **DB Persistence** (`db.py:insert_message_and_observations`)
   - `hl7_messages`: stores raw_hl7 (TEXT), patient_id, patient_first/last_name, patient_dob, patient_sex, fhir_bundle_json
   - `observations`: stores code, display, value_num/value_raw, unit, ref_low/high, flag, obs_datetime, status, alert_level, alert_message, source
   - **Raw HL7 and full FHIR bundle both stored unencrypted in plaintext**
   - No deduplication on MSH-10 (message_control_id)
   - Hard limit: rejects inserts once count >= 1300

8. **Parse Session Lifecycle** (`db.py`, `api.py`)
   - Session states: validated -> persisting -> persisted
   - TTL: SECURITY_HL7_PARSE_MINUTES (default 10 min) -- checked on read only, not enforced by schema
   - **Orphaned sessions**: if persistence fails mid-transaction, session stuck in 'persisting' forever
   - No active cleanup job visible in codebase

9. **API Response** (`api.py`)
   - POST /oru/parse returns: patient (real names), clinical_summary, structured_observations, **full FHIR bundle**, hl7_ack, ai_analysis
   - GET /messages/{id} returns raw_hl7 if `SECURITY_SHOW_PROTECTED_OUTPUT=true` (debug flag)
   - **Full FHIR bundle returned without role-based access control or code filtering**

---

## Client-Trusted Fields

Fields extracted from raw HL7 and written to DB or FHIR without validation:

| Field | Source | Destination | Validated? |
| :--- | :--- | :--- | :--- |
| PID-3 patient_id | HL7 | hl7_messages.patient_id, FHIR Patient.id | No |
| PID-5 patient_name | HL7 | hl7_messages.patient_first/last_name, FHIR Patient.name | No |
| PID-7 dob | HL7 | hl7_messages.patient_dob, FHIR Patient.birthDate | String truncation only |
| PID-8 sex | HL7 | hl7_messages.patient_sex, FHIR Patient.gender | M/F/U/O mapping only |
| OBX-2 value_type | HL7 | observations.status | No |
| OBX-3 code | HL7 | observations.code, alert matching | No -- enables alert injection |
| OBX-3 display | HL7 | observations.display | No |
| OBX-5 value | HL7 | observations.value_num / value_raw | Float parse or string |
| OBX-6 unit | HL7 | observations.unit | CE -> ER7 string |
| OBX-7 reference_range | HL7 | observations.reference_low / reference_high | Split on "-" only |
| OBX-8 flag | HL7 | observations.flag | Single char, no whitelist |
| OBX-11 status | HL7 | observations.status -> FHIR Observation.status | F/P mapping only |
| OBX-14 obs_datetime | HL7 | observations.observation_datetime | HL7->ISO string only |
| NTE-3 comment | HL7 | observations.notes | hl7_guard text check |
| MSH-3 sending_app | HL7 | ACK receiving_app | Echoed |
| MSH-4 sending_facility | HL7 | ACK | Echoed |
| MSH-10 control_id | HL7 | parse session identifier, ACK | Echoed; no uniqueness check |

---

## Risks / Bypasses

### CRITICAL

**C1 -- Unvalidated OBX-3 Code Enables False Alert Injection**
- Attacker sends OBX with code matching a high-alert LOINC (e.g., `49563-0` Troponin I) and a fabricated value
- `check_alert()` matches on code only; triggers CRITICAL "Possible Myocardial Infarction" alert
- Alert stored in DB and returned in API response; clinician may act on false data
- **Action**: Add LOINC code allowlist; validate code format before alert matching

**C2 -- Raw HL7 Stored Unencrypted and Conditionally Exposed**
- Entire HL7 message stored as plaintext TEXT in `hl7_messages.raw_hl7`
- GET /messages/{id} returns raw_hl7 if `SECURITY_SHOW_PROTECTED_OUTPUT=true`
- If this flag is set in production, complete PHI is exposed to all API callers
- **Action**: Encrypt raw_hl7 at rest; remove or hard-disable the debug flag in production builds

**C3 -- Full FHIR Bundle Returned Without Access Control**
- POST /oru/parse returns complete FHIR Bundle with all clinical observations
- No role-based filtering; sensitive codes (psychiatric, HIV, mental health) returned to all callers
- **Action**: Add attribute-based access control before returning FHIR; filter sensitive codes by role

**C4 -- MLLP Decoder Uses Lossy UTF-8 Encoding**
- `mllp_server.py`: `decode("utf-8", errors="replace")` silently replaces bad bytes with U+FFFD
- Malformed UTF-8 can pass through corrupted, triggering parser errors or incorrect data persistence
- **Action**: Log and reject messages with non-UTF8 bytes; do not silently replace

### WARNING

**W1 -- No Idempotency on Message Control ID**
- `run_oru_pipeline()` does not check if MSH-10 already exists in DB
- Same HL7 sent twice creates duplicate records; duplicate observations; double alerts
- **Action**: Check (sending_app, sending_facility, message_control_id) uniqueness before insert; return existing record if duplicate

**W2 -- Parse Session Orphan Accumulation**
- If persistence fails mid-transaction, session stuck in 'persisting' state indefinitely
- TTL only checked on read; no active cleanup job
- **Action**: Add background cleanup job; mark sessions stuck in 'persisting' > 2x TTL as 'failed'

**W3 -- 1300 Message Hard Limit Has Race Condition**
- Count check and insert are not atomic; two concurrent requests can both pass the check
- Once at limit, all new messages silently rejected
- **Action**: Add database-level constraint or use atomic ROWID check; make limit configurable; add monitoring alert

**W4 -- Numeric Precision Loss in Float Coercion**
- `_parse_value()` stores values as float; alert thresholds compared as float
- Rounding errors can cause borderline values to miss or false-trigger alerts
- **Action**: Store as DECIMAL or string; use Decimal type for threshold comparisons

**W5 -- Clinical Summary Generated Without Value Validation**
- `_basic_clinical_summary()` stringifies raw observation values directly
- Invalid values (e.g., OBX-5 = "POSITIVE" for Glucose) produce nonsensical summary text
- LLM receives invalid data and may hallucinate
- **Action**: Validate value against OBX-2 type before summary generation; flag anomalies

### INFORMATIONAL

**I1 -- FHIR Observation IDs Not Stable**
- `id=f"obs-{idx}"` uses loop counter; same HL7 parsed twice produces identical IDs for different records
- FHIR spec expects stable UUIDs for resource correlation
- **Action**: Generate deterministic UUIDs from hash(message_id + obs_index)

**I2 -- Reference Range Parsing Fragile**
- Splits on first "-"; fails on negative ranges or ranges without hyphen
- **Action**: Improve parser; log parse failures as governance events

**I3 -- Observation Timestamps Not Validated**
- OBX-14 accepted as-is; no check that obs_datetime <= received_at
- Future or nonsense timestamps accepted silently
- **Action**: Log timestamp anomalies; reject dates far outside valid clinical range

**I4 -- Alert Coverage Is Minimal (3 Rules)**
- Only Troponin, Glucose, Potassium covered
- Most lab codes produce no alert even if critically abnormal
- **Action**: Expand alert rules or integrate external clinical decision support

**I5 -- AI-Extracted Observations Have Fragile Deduplication**
- `_merge_llm_output()` deduplicates on (code, value) string match only
- Equivalent observations with different units or display names may duplicate
- **Action**: Normalize units before dedup; use code-only match with value tolerance

---

## Recommended Implementation Notes

1. **LOINC code allowlist** -- maintain canonical list of valid codes; reject OBX-3 not in allowlist; log to governance_events
2. **Encrypt raw_hl7 at rest** -- AES-256; key in secrets manager; audit all accesses; consider tiered retention (30-day raw, then delete or archive)
3. **FHIR attribute-based access control** -- filter by role before returning bundle; redact sensitive code systems without explicit grant
4. **Idempotency on message_control_id** -- add UNIQUE constraint on (sending_app, sending_facility, message_control_id); return existing record on duplicate
5. **Parse session cleanup job** -- hourly cleanup of expired and orphaned sessions; add governance metrics
6. **MLLP encoding hardening** -- reject non-UTF8; add frame size limit; add per-sender rate limiting; require TLS if in production
7. **Deterministic FHIR UUIDs** -- hash(message_id + obs_index) for stable observation IDs
8. **Decimal precision for alert thresholds** -- use Python Decimal for all clinical value comparisons

---

## Tests To Add

1. `test_alert_injection_blocked` -- fake Troponin LOINC code with fabricated value must not trigger clinical alert after code validation is added
2. `test_duplicate_message_control_id` -- same MSH-10 sent twice; only one record in DB
3. `test_raw_hl7_redacted_without_debug_flag` -- GET /messages/{id} must redact raw_hl7 by default
4. `test_fhir_bundle_observation_ids_stable` -- parse same HL7 twice; observation UUIDs identical
5. `test_parse_session_expires_after_ttl` -- expired session returns None on claim
6. `test_orphaned_session_cleanup` -- session stuck in 'persisting' is cleaned up after 2x TTL
7. `test_db_hard_limit_enforced` -- insert 1300 messages; 1301st rejected with clear error
8. `test_mllp_rejects_non_utf8` -- send malformed UTF-8 bytes; message is rejected, not silently corrupted
9. `test_reference_range_negative_numbers` -- OBX-7 with negative lower bound parses correctly
10. `test_observation_datetime_future_rejected` -- OBX-14 far in future is logged as anomaly
11. `test_sql_injection_in_observation_code` -- OBX-3 with SQL payload; hl7_guard blocks it
12. `test_ai_extraction_no_duplicate_observations` -- LLM extraction of value already in base obs does not duplicate

---

## Open Questions

1. Is the 1300 message limit intentional or a demo artifact? Should it be configurable with a retention policy?
2. Should raw_hl7 be stored at all, or only FHIR? Raw HL7 rarely needed for clinical decisions; increases breach surface.
3. Is `SECURITY_SHOW_PROTECTED_OUTPUT` ever set in non-development environments? Should be removed from production builds.
4. What is the intended access control model for the FHIR bundle response? All callers see all data, or role-scoped?
5. Is MLLP server in production or demo only? If production: requires TLS, sender authentication, rate limiting.
6. Is there a LOINC license or subscription available for code validation?
7. Should duplicate HL7 messages be rejected or deduplicated silently? (Implications for HL7 retry protocols)
8. Are there HIPAA / HITECH compliance requirements that mandate encryption-at-rest and audit trail?
