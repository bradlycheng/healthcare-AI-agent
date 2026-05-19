# Lead Mapping Summary: Phase 0

## Purpose

This summary combines the four read-only explorer reports. It is the gate before Phase 1 kernel-spine implementation.

## Phase 0 Status

Complete. All four required maps were produced:

- `01-explorer-query-flow.md`
- `02-explorer-hl7-messages.md`
- `03-explorer-warden-guards.md`
- `04-explorer-storage-audit-admin.md`

## Highest-Risk Bypasses

1. `/api/query` legacy fallback can call ungated `process_query` after agent failure.
2. `/messages` can persist client-supplied patient, observations, summary, FHIR, source, and alert fields as authority.
3. Deep mode sends raw question to reflection LLM before Warden tokenization.
4. SQL generation and RAG embedding can call LLM/Bedrock outside a governed gateway with real PHI.
5. Warden v1 lacks grants, session binding, exact schema validation, scoped tokens, and canonical PHI-free audit.
6. Token restore can restore guessed/stale/user/RAG-injected tokens if they match the request token map.
7. Read/patient/timeline/message endpoints expose PHI outside the planned kernel/output-policy gates.
8. JSONL audit is not canonical, not DB-backed, lacks request/session IDs, and does not enforce PHI-free payloads.

## Dangerous Entrypoints Mapped

- `POST /api/query`
- `POST /oru/parse`
- `POST /messages`
- `GET /messages`
- `GET /messages/{message_id}`
- `GET /messages/{message_id}/observations`
- `GET /patients`
- `GET /patients/{patient_id}/timeline`
- `GET /patients/{patient_id}/summary`
- `DELETE /messages`
- `POST /admin/reset`

## Direct LLM / Model Touchpoints Mapped

- `app/healthcare_agent.py`: planner, synthesis, deep reflection.
- `app/query_assistant.py`: SQL generation and result formatting.
- `app/agent.py`: HL7 note/text extraction.
- `app/patient_timeline.py`: patient journey summary.
- `app/embeddings.py`: Bedrock Titan embeddings for RAG.
- `app/llm_client.py`: low-level Bedrock caller.

## Persistence Paths Mapped

- `/oru/parse persist=true` -> `run_oru_pipeline` -> `insert_message_and_observations`.
- `/messages` -> accepts client clinical JSON -> `insert_message_and_observations`.
- Startup pruning deletes some `hl7_messages`/`observations` but does not govern all related state.
- No parse-session, conversation-state, result-ref, demo-session, governance-events, or protected-trace tables currently exist.

## Client-Authority Risks

- `/messages` trusts client patient/observation/FHIR/summary/source/alert fields.
- Client can save parse results without proving they came from server parse.
- Browser edit/manual-observation flow has no server-side provenance authority model.
- Client-visible IDs such as `message_id` and `patient_id` are effectively direct authority.

## Phase 1 Required Implementation Targets

- Add kernel contracts/config/audit helper.
- Add server-issued demo session ownership.
- Add `governance_events` as canonical PHI-free audit.
- Add `llm_gateway.py` and migrate/block direct LLM boundaries.
- Route `/api/query`, `/oru/parse`, and `/messages` through kernel gates.
- Remove or block ungated `/api/query` fallback.
- Add `hl7_parse_sessions` with status, TTL, session ownership, raw hash, and server-owned result.
- Make `/messages` persist only validated server-owned parse sessions.
- Add Warden v2 exact-schema + grant skeleton.
- Add fail-closed behavior for unsupported/unknown cases.

## Phase 1 Tests To Prioritize

- Static test: no direct low-level LLM imports outside gateway-allowed modules.
- `/api/query` failure does not call ungated `process_query`.
- Deep mode cannot call raw-question reflection outside gateway/Warden.
- `/messages` rejects client-created clinical authority.
- Parse-session tests for missing, expired, wrong-session, already-used, and tampered parse IDs.
- Tool execution fails without grant.
- Exact schema rejects missing required fields and extra fields.
- `governance_events` rejects PHI-bearing keys.
- Timeout/interruption cannot commit memory or persist partial authority.
- Valid demo query and valid ORU parse preview still work.

## Open Decisions For Phase 1

- Use strict default: legacy `process_query` fallback is disabled unless wrapped by kernel.
- Use strict default: `/messages` transition mode is off unless needed for temporary UI compatibility.
- Keep admin password-only for this slice, but route attempts/successes through `governance_events`.
- Keep `sql_used` treated as protected/debug trace; do not put it in PHI-free audit.
- Prefer schema changes in `init_db` with idempotent `CREATE TABLE IF NOT EXISTS` for this prototype unless a migration framework is introduced later.

## Gate Result

Phase 0 mapping is complete. Phase 1 kernel-spine implementation can start after this summary is reviewed.
