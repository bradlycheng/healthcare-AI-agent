# Agent Report: Explorer D - Storage, State, Audit, Admin

## Assignment

Map DB setup, reset/admin paths, trace storage, session gaps, TTL/index needs, and audit risks. No files edited.

## Files Inspected

- `app/db.py`
- `app/api.py`
- `app/warden.py`
- `app/healthcare_agent.py`
- `app/query_assistant.py`
- `app/agent.py`
- `app/patient_timeline.py`
- `app/seed.py`
- `app/models.py`
- `app/crud.py`
- `web/dashboard.js`
- `web/script.js`
- reset/security test files
- `tests/test_e2e_warden.py`
- `docs/security-kernel-plan.md`
- `.env` and `.env.example` for admin/reset posture only; secret values not repeated.

## Current Flow

- SQLite schema currently includes `hl7_messages`, `observations`, `visits`, `medications`, `diagnoses`, and `contacts`.
- DB connections enable WAL, busy timeout, synchronous normal, and foreign keys.
- HL7 ingestion has two persistence paths:
  - `/oru/parse` can persist through `run_oru_pipeline`.
  - `/messages` can persist client-supplied raw HL7, patient, observations, and FHIR.
- There is no parse session table or server-owned `parse_id`.
- `/api/query` returns answer, SQL, row count, sources, tools, and trimmed reasoning trace.
- Frontend conversation state is browser memory only; history is sent back to `/api/query`.
- There is no server-owned `conversation_id`, `conversation_states`, or result-ref table.
- Audit is Warden JSONL only; there is no `governance_events` table.
- Startup prunes old `hl7_messages` and `observations`, but not all related clinical/trace/state data.
- `DELETE /messages` and `POST /admin/reset` are password-protected. `/admin/reset` has an async lock; `DELETE /messages` does not.

## Risks / Bypasses

- No session ownership boundary exists; protected objects are global DB records.
- Client-visible IDs like `message_id` and `patient_id` act as direct authority.
- Missing planned tables: `demo_sessions`, `hl7_parse_sessions`, `conversation_states`, `conversation_result_refs`, `ai_interactions`, and `governance_events`.
- `/messages` can persist client-tampered parse/result payloads.
- Deep mode sends raw question into reflection before Warden.
- Legacy fallback bypasses Warden.
- `sql_used` can contain PHI and is returned to browser.
- JSONL audit is append-only best effort, unbounded, and not canonical compliance audit.
- Admin attempts/successes are printed but not durably PHI-safe audited.
- CORS allows all origins while reset/admin rely on shared password.
- Startup TTL can delete messages/observations while leaving visits/medications/diagnoses inconsistent.
- No DB indexes exist for common lookup paths or future TTL cleanup.

## Recommended Implementation Notes

- Add canonical `governance_events` table and helper with safe fields only.
- Add server-issued `demo_sessions` with expiry and indexes.
- Add `hl7_parse_sessions` with parse ID, session ID, raw HL7 hash, status, server parse payload/result reference, note policy result, timestamps, and expiry.
- Add `conversation_states` and optional `conversation_result_refs` with typed metadata, session ID, status, and TTL.
- Add protected `ai_interactions` only if traces are needed; never use it as PHI-free audit.
- Make `/messages` persist only a validated, unexpired parse session owned by the same session.
- Route `/api/query`, `/oru/parse`, `/messages`, reads, and admin/reset through a kernel guard that emits `governance_events`.
- Disable ungated fallback or route it through grant/audit/session checks.
- Move deep reflection inside tokenization/gateway or disable it.
- Add indexes for patient/date/message lookups and all session/TTL tables.
- Replace startup-only cleanup with explicit TTL/expiration jobs.

## Tests To Add

- Session creation, refresh, expiry, and wrong-session denial.
- `/oru/parse` preview creates parse session; `/messages` rejects missing/expired/wrong-session/used/tampered parse IDs.
- Conversation/result refs fail closed when stale, guessed, cross-session, or out of scope.
- Deep mode PHI never reaches reflection LLM before tokenization.
- Agent failure cannot bypass Warden/table policies.
- Legacy SQL cannot read `contacts` or non-allowlisted tables/columns.
- `governance_events` rejects PHI-bearing payload keys and includes request/session/reason metadata.
- Admin reset success/failure/concurrency emits audit events and requires direct admin auth.
- TTL cleanup expires all owned state without orphaning related rows.
- Public traces do not include raw tool results, raw HL7, token maps, DOB, or names unless intentionally released.

## Open Questions

- Should demo reset preserve `contacts`?
- Should `sql_used` stay visible or move behind protected/debug mode?
- What TTL applies to durable clinical data versus transient parse/session/conversation state?
- Should Phase 1 add migrations, or keep schema creation in `init_db` for now?
- Should admin auth stay password-only for this slice, or add CSRF/session binding immediately?
