# Explorer B Report: Endpoint Output Map

## Scope

Read-only map of the current endpoint and output-policy posture for:

- `/api/query`
- `/oru/parse`
- `/messages`
- message/patient read endpoints
- `sql_used`
- raw HL7 and FHIR exposure
- note/text-column paths
- `governance_events` audit coverage

Current workspace note: this map reflects the on-disk state observed during the pass. The tree already had collaborator edits in `app/api.py`, `app/security_validation.py`, `app/safe_memory.py`, `warden_audit.jsonl`, web files, `agent.db`, and a new `app/reference_resolver.py`; this report does not revert or overwrite them.

## Current Files And Functions

### `app/api.py`

- `QueryRequest` / `QueryResponse`
  - `QueryResponse.sql_used` still exists as a public schema field.
  - Current response population gates it with `_debug_flag("show_sql_used")`, returning an empty string by default.
- `_debug_flag(name)`
  - Reads `SECURITY_CONFIG["debug"]`.
  - Currently used for `show_sql_used` and protected message-detail output.
- `_audit_read_endpoint(request, response, component, reason_code, payload)`
  - Creates a request ID, gets/creates demo session, and emits `governance_events` through `emit_governance_event`.
- `/api/query` via `query_assistant_endpoint`
  - Creates request/session IDs.
  - Loads safe memory state.
  - Runs reference resolution through `resolve_safe_references`.
  - Classifies intent, builds a grant with subject from resolution, runs the agent through `_run_agent_with_timeout`, and commits safe memory only after success.
  - Emits events for received query, reference resolution, intent allow/deny, completion, timeout, failure, exception, and memory commit/skip.
  - Returns `answer`, `highlights`, `row_count`, `sources`, `reasoning_trace`, `tools_used`, clarification fields, and default-hidden `sql_used`.
- `/oru/parse` via `parse_oru_endpoint`
  - Sanitizes HL7, validates through `validate_hl7_message`, rejects direct persist by default, enforces timeout, runs `run_oru_pipeline`, creates a server-owned parse session on preview, and emits governance events.
  - Response still returns patient identity, clinical summary, observations, full FHIR bundle, ACK, AI analysis, and parse ID. It does not return raw HL7 directly.
  - Preview parse session stores `raw_hl7`, patient, observations, FHIR, and AI analysis in `hl7_parse_sessions.parse_result_json`.
- `/messages` via `save_message_endpoint`
  - Default path requires same-session `parse_id`; atomically claims parse session and persists only server-owned parse result.
  - Legacy compatibility branch can still persist client-supplied raw HL7, patient, observations, and FHIR if `SECURITY_ALLOW_LEGACY_MESSAGES=true`.
  - Emits governance events for missing parse ID, legacy save, invalid/expired parse ID, parse-session persistence, and save exception.
- `GET /messages`
  - Returns message list with patient ID, first name, last name, DOB, sex, timestamp.
  - Audited through `_audit_read_endpoint` with limit/offset/total only.
- `GET /messages/{message_id}`
  - Selects `raw_hl7` and `fhir_bundle_json`.
  - Redacts `raw_hl7` and returns an empty redacted FHIR bundle unless `SECURITY_SHOW_PROTECTED_OUTPUT=true`.
  - Still returns patient ID, name, DOB, and sex directly.
  - Audited through `_audit_read_endpoint`.
- `GET /messages/{message_id}/observations`
  - Returns observation code/display/value/unit/reference/flag/status/alert fields.
  - Uses `_obs_value`, which returns `value_raw` when `value_num` is absent.
  - Audited through `_audit_read_endpoint`.
- Patient reads:
  - `GET /patients` returns patient identifiers and demographics, audited.
  - `GET /patients/{patient_id}/timeline` returns patient identifiers plus visits/observations, audited. Audit payload includes `patient_id`, which should be redacted by `audit_safe_payload`.
  - `GET /patients/{patient_id}/summary` calls `generate_journey_summary`, returns generated summary, audited.
- Other read-ish endpoints:
  - `GET /api/document/{filename}` reads bundled docs with filename validation and rate limiting, but does not emit governance audit.
  - Static/UI endpoints and `/health`/`/ping` are not PHI read endpoints and are not governed.

### `app/security_validation.py`

- `SECURITY_CONFIG`
  - Contains `debug.show_sql_used` and `debug.show_protected_output`, both false by default.
  - Contains compatibility toggles for legacy `/messages` and direct ORU persist.
- `AUDIT_BLOCKED_KEYS`
  - Blocks/redacts raw text, raw HL7, question/history/answer, token maps, patient identifiers, DOB, FHIR, and SQL keys.
- `audit_safe_payload`
  - Redacts only by exact key match, recursively for dictionaries.
  - Allows scalar values for non-blocked keys, and scalar list items.
- `emit_governance_event`
  - Current canonical PHI-free audit path into `db.insert_governance_event`.

### `app/db.py`

- `governance_events` table exists with request/session/component/action/reason/payload/created_at.
- `insert_governance_event` writes audit rows.
- `hl7_parse_sessions` stores `raw_hl7_hash`, `parse_result_json`, and `note_policy_result_json`.
- `create_hl7_parse_session`, `claim_hl7_parse_session`, `mark_hl7_parse_session_persisted` implement parse-session ownership/status.
- `insert_message_and_observations` persists:
  - `hl7_messages.raw_hl7`
  - patient identifiers/demographics
  - `fhir_bundle_json`
  - observation `value_raw` for non-numeric values
  - no separate persisted `notes` column; NTE/text notes can become transient `notes` in parse output or stored text values/extracted observations.

### `app/healthcare_agent.py`

- `HealthcareAgent.run`
  - Uses Warden request scope, anonymizes question/history, validates tool calls, tokenizes tool results before synthesis, then deanonymizes answer/highlights.
  - Returns `sql_used` internally from the database tool, but API now hides it unless debug is enabled.
  - Adds `token_restore_summary` into `safe_metadata`.
- `_tool_query_database`
  - Generates SQL, validates with SQLGuard, executes read-only query, returns `results`, `row_count`, `sql`, explanation, context, and sources.
- `_tool_get_patient_context`
  - Uses `get_patient_timeline` and can return patient identifiers and observations into tool results before Warden anonymizes for synthesis.

### `app/sql_guard.py`

- `DEFAULT_ALLOWED_COLUMNS` excludes `hl7_messages.raw_hl7` and `hl7_messages.fhir_bundle_json`.
- `observations.value_raw` is allowlisted.
- Existing tests deny direct SQL reads of raw HL7 and FHIR bundle columns.
- No contextual note/text policy is applied to `observations.value_raw`; the guard cannot currently distinguish a benign string lab value from a text note payload.

### `app/hl7_guard.py`, `app/hl7_parser.py`, `app/agent.py`

- `validate_hl7_message`
  - Validates ORU shape and applies note policy to NTE-3 plus text-like OBX-5.
  - Emits only issue codes/count metadata, not raw note text.
- `parse_oru`
  - Attaches NTE text into `notes` on the previous observation.
  - Creates placeholder `NOTE` observation when NTE appears before any OBX.
  - Text OBX-5 values become observation `value`.
- `run_oru_pipeline`
  - Sends collected notes/text observations into `hl7_note_extraction` when LLM note extraction is enabled.
  - Persists raw HL7 and FHIR only through DB/protected paths.

### `app/patient_timeline.py`

- `get_patient_timeline`
  - Selects `raw_hl7` from `hl7_messages` but does not use it in the returned structure.
  - Returns patient identifiers and observation values, using `value_raw` when numeric value is absent.
- `generate_journey_summary`
  - Current prompt withholds direct identifiers, but still uses clinical observation strings derived from stored values.

## Gaps Against The Plan

- Read endpoints are audited, but they do not build read grants or enforce output-field policy. Patient/message list/detail/timeline still directly expose patient ID, name, DOB, and sex.
- `/messages/{message_id}` now redacts raw HL7 and FHIR by default, but the response model still includes those fields and debug mode can expose them. There is no per-session/role output grant around the debug exposure.
- `/oru/parse` response still returns full FHIR and direct patient identifiers as preview output. That may be intentional for the demo UI, but it is not yet behind an explicit output-field grant or protected-output mode.
- `sql_used` is hidden by default, which closes the obvious browser disclosure. The schema and internal result still carry it, and debug exposure is controlled only by environment config, not request/session/actor authorization.
- `observations.value_raw` remains an unclassified text output path. It can carry text OBX clinical notes, AI-extracted note findings, or string lab values, and is returned by `/messages/{id}/observations`, patient timeline, patient context tool results, and SQL queries.
- Note policy is enforced at HL7 ingress for NTE/text OBX, but retrieved legacy text values are not tagged as `legacy_unverified_note` or tainted evidence.
- `hl7_parse_sessions.parse_result_json` stores raw HL7/FHIR/patient/AI analysis as protected server state. That is not PHI-free audit, but it needs retention/cleanup and must not be exposed through future admin/debug reads.
- `audit_safe_payload` redacts exact blocked keys, but nonstandard names such as `subject`, `resolved_subject`, `patient`, `name`, `mrn`, `identifier`, or nested custom keys could carry PHI unless callers keep using safe counts/booleans.
- `governance_events` coverage is good for `/api/query`, `/oru/parse`, `/messages`, message reads, and patient reads. It is absent for `/api/document/{filename}`, static reads, health/ping, and admin/reset paths in the inspected slice.
- Admin/reset audit coverage remains outside this endpoint/output hardening map. The plan calls for explicit admin grant/audit metadata.
- `get_patient_timeline` still selects `raw_hl7` unnecessarily. Even though it is not returned, it widens accidental exposure risk in future edits and tool debugging.

## Exact Tests Needed

- `test_api_query_hides_sql_used_by_default`
  - Monkeypatch `run_agent_query` to return a SQL string containing a patient predicate.
  - Ensure `/api/query` response has `sql_used == ""` when `SECURITY_SHOW_SQL_USED` is false.
  - Ensure `governance_events` payload does not contain the SQL.
- `test_api_query_sql_used_requires_debug_flag`
  - Enable `SECURITY_CONFIG["debug"]["show_sql_used"]` with monkeypatch.
  - Verify SQL appears only in that mode.
  - This locks current debug behavior before deciding whether to replace it with grant-based protected output.
- `test_message_detail_redacts_raw_hl7_and_fhir_by_default`
  - Seed/save a message with recognizable raw HL7 and FHIR entry.
  - `GET /messages/{id}` must return `[REDACTED_PROTECTED_OUTPUT]` for raw HL7 and a redacted empty bundle by default.
  - Audit payload must not contain raw HL7, FHIR, names, DOB, or stack traces.
- `test_message_detail_protected_output_flag_is_explicit`
  - Temporarily enable `SECURITY_CONFIG["debug"]["show_protected_output"]`.
  - Verify raw HL7/FHIR exposure happens only under that flag.
  - Mark this as temporary until a grant/actor policy replaces the flag.
- `test_read_endpoints_emit_phi_free_governance_events`
  - Exercise `/patients`, `/patients/{patient_id}/timeline`, `/patients/{patient_id}/summary`, `/messages`, `/messages/{id}`, and `/messages/{id}/observations`.
  - Assert an event exists for each component/reason code.
  - Assert serialized events exclude raw HL7, FHIR bundle text, patient names, DOBs, raw answer text, SQL, token maps, and stack traces.
- `test_oru_parse_preview_audit_excludes_raw_hl7_fhir_and_patient_identity`
  - Parse a valid ORU with known patient name/DOB.
  - Assert response may include current preview fields, but `governance_events` contains only safe counts/IDs and redaction markers.
- `test_oru_parse_preview_output_policy_is_documented_or_gated`
  - Add a pending/failing test to encode the desired next policy: full FHIR and direct identifiers either require protected-output authorization or are replaced by safe preview fields.
- `test_observation_value_raw_note_path_is_tainted_or_blocked`
  - Ingest a text OBX or NTE-derived note value.
  - Verify `/messages/{id}/observations`, patient timeline/context, and SQL query paths either mark it as tainted evidence or withhold it according to the chosen note-output policy.
- `test_sql_guard_note_column_policy_for_value_raw`
  - Keep existing raw HL7/FHIR SQL denials.
  - Add a case for generated SQL selecting `observations.value_raw` from note-like rows. Expected behavior should be deny, taint, or require a special note grant; current static allowlist is insufficient.
- `test_get_patient_timeline_does_not_select_raw_hl7`
  - Static or monkeypatch DB assertion that timeline retrieval no longer selects unused `raw_hl7` after cleanup.
- `test_api_document_read_audit_or_explicit_exemption`
  - Either require a governance event for `/api/document/{filename}` or add a test documenting why bundled document reads are outside PHI audit scope.
- `test_admin_reset_governance_audit`
  - Direct reset/admin success, auth failure, disabled password, and concurrency/lock paths emit PHI-free admin governance events.

## Integration Cautions

- Do not remove response fields blindly. The current UI may depend on `/oru/parse` returning patient, observations, FHIR, ACK, AI analysis, and `parse_id`; `/messages/{id}` may also expect `raw_hl7`/`fhir_bundle` keys even when redacted.
- Keep `sql_used` as protected/debug trace, not PHI-free audit. If it is exposed later, prefer an explicit protected-output grant over a global flag.
- Treat `value_raw` as the next tricky boundary. It is both a normal string-lab storage field and a possible note/clinical-text carrier.
- Do not trust `parse_result_json` as public-safe just because it is server-owned. It is protected PHI state and should stay behind session/status/TTL checks.
- Keep `governance_events` payloads boring: counts, booleans, reason codes, component/action, IDs only when they are non-PHI or redacted by helper.
- Coordinate with the active safe-memory/reference-resolver edits. `/api/query` now resolves references before classification and commits only typed safe metadata; output hardening should not widen memory scope or reintroduce raw history/answer storage.
- Avoid using `show_protected_output` as a production authorization model. It is useful for compatibility/debugging, but the plan calls for session/grant/output-field enforcement.
- If note tainting is added, update SQLGuard, patient timeline, message observation reads, safe-memory extraction, and agent synthesis together so one path does not silently bypass the policy.
