# Reviewer Security Pass: Next Hardening Slice

Date: 2026-05-20

Scope: current working tree plus `docs/agent-reports/next-hardening/{00,01,02}-*.md`. Production code was not modified in this pass.

## Findings

### P1 - Client-supplied history can still act as authority for reference resolution and direct answers

`/api/query` resolves safe references before classification, but then still passes `req.history` into the agent at `app/api.py:508-514`. The agent sends the last five client-supplied history messages into the planning prompt at `app/healthcare_agent.py:542-565`, and the planner is explicitly allowed to return `direct_answer` from conversation history at `app/healthcare_agent.py:179-180` and `app/healthcare_agent.py:370-384`. The SQL generator receives that same history at `app/healthcare_agent.py:450-452` and `app/healthcare_agent.py:754`, and its prompt tells the LLM to identify patients from chat history and prior assistant answers at `app/query_assistant.py:115-120` before embedding `CHAT HISTORY` into the SQL prompt at `app/query_assistant.py:461-467`.

Bypass shape: a request like `What about BP?` does not match `REFERENCE_RE` in `app/reference_resolver.py:10-12`, so it reaches the agent unchanged. A client can attach fabricated assistant history such as "John Smith (P123)..." and the SQL prompt is instructed to use it as the patient source. This reintroduces stale authority and client-created truth even though the safe-memory resolver itself does not read raw history.

Concrete missing tests:

- Add an API test where `history` contains a fabricated prior assistant answer and no server safe state; assert the classifier/agent/SQL generator do not use it to resolve a patient.
- Add a direct `HealthcareAgent`/SQL-generation guard test that `history` is not present in planning or SQL prompts as authority-bearing context.
- Add a regression for `What about BP?`/`what about glucose?` with no safe state; expected result should be clarification or no patient filter, never history-derived subject binding.

### P1 - Resolved patient IDs are appended into LLM-visible prompt text

`resolve_safe_references` returns a governed question by appending `[Resolved safe reference: patient_id=...]` at `app/reference_resolver.py:67`. The API sends that full text to `classify_query_intent` at `app/api.py:451-455`, and the classifier directly embeds the user request in an LLM prompt at `app/intent_classifier.py:46-49` and `app/intent_classifier.py:107-120`. The same governed question is then passed to the agent at `app/api.py:508-514`.

This leaks a direct patient identifier into at least the intent-classification LLM path before Warden tokenization. It also turns structured server authority into natural-language prompt content that later prompts can reinterpret. The endpoint test currently locks in this risky shape by asserting `"patient_id=PREF1"` is present in the classified question at `tests/test_endpoint_governance.py:354`.

Concrete missing tests:

- Replace the current assertion with one proving the classifier receives no raw `patient_id=` text while `grant.subject` is set.
- Add a spy around `intent_classification` proving resolved subjects are carried only as structured metadata/grant fields, not interpolated into prompt text.
- Add a PHI-leak regression for patient IDs in classifier/planner prompt inputs.

### P1 - Grant subject is not enforced at the tool or SQL boundary

The API correctly passes `subject=resolution.subject` into `build_query_grant` at `app/api.py:471-478`, and the test checks only that the API-level grant contains the subject at `tests/test_endpoint_governance.py:331-356`. Enforcement stops there. Warden checks grant expiry and allowed tool membership at `app/warden.py:426-480`, but `_validate_get_patient_context` only requires that some `patient_id` or `patient_name` exists at `app/warden.py:649-662`; it does not compare the requested patient with `grant.subject`.

The SQL path also discards the endpoint grant. `_tool_query_database` builds a fresh `agent_internal` grant at `app/healthcare_agent.py:765-776`, losing the original session, request, scope, subject, and output-field restrictions before SQLGuard runs. SQLGuard itself validates tables/columns/limits but has no subject predicate enforcement in `app/sql_guard.py:207-241`.

Bypass shape: after a safe reference narrows to `P1`, an LLM tool call can request `get_patient_context` for `P2` and still pass Warden as long as the tool is allowed. Similarly, a SQL query can omit the subject predicate or query a cohort under a subject-bearing grant because subject is not part of validation.

Concrete missing tests:

- Warden unit test: grant with `subject="P1"` must deny `get_patient_context` for `patient_id="P2"` and allow `P1`.
- Agent/tool test: `_tool_query_database` must validate with the original endpoint grant, not a freshly built `agent_internal` grant.
- SQLGuard/grant test: subject-scoped grants must require an equivalent patient predicate or inject/enforce a server-side subject constraint.

### P2 - Timeout response does not cancel running work and can create unbounded residual execution

`_run_agent_with_timeout` creates a new `ThreadPoolExecutor` per request, waits for the configured timeout, and then calls `executor.shutdown(wait=False, cancel_futures=True)` at `app/api.py:291-297`. For an already-running LLM/tool call, `cancel_futures=True` does not stop the thread. The endpoint returns a safe timeout response at `app/api.py:516-529`, but the worker can continue consuming LLM, DB, RAG, and Warden resources after the client receives "no memory was committed."

The existing timeout test at `tests/test_endpoint_governance.py:447-490` verifies the immediate response and memory state, but it does not prove the worker stopped, that no late Warden/audit side effects occurred, or that repeated timeouts cannot accumulate abandoned worker threads. This matters for timeout/memory behavior because the safety claim is only about the endpoint commit path, not about residual processing or resource exhaustion.

Concrete missing tests:

- Instrument a slow agent that records after the timeout; assert no post-timeout tool/LLM/DB action can occur, or explicitly mark the current behavior as a known residual-risk fail.
- Add a load-style unit test around repeated timeouts to prove thread count/resource use remains bounded.
- Prefer cooperative cancellation propagated into LLM/RAG/SQL calls, or isolate timed work in a cancellable process/job boundary.

### P2 - PHI-bearing preview and read outputs remain ungated by output grants

The message detail endpoint now redacts raw HL7 and FHIR by default at `app/api.py:1259-1272`, but other read paths still return identifiers and demographics without a read grant. `/patients` returns patient ID, name, DOB, and sex at `app/api.py:679-690`; `/patients/{patient_id}/timeline` returns the same at `app/api.py:714-747`; `/messages` returns patient identity fields at `app/api.py:1180-1211`; `/messages/{message_id}` still returns patient identity fields at `app/api.py:1251-1272`.

`/oru/parse` preview returns `patient`, `structured_observations`, full `fhir_bundle`, and `ai_analysis` at `app/api.py:1148-1155`, while the server-owned parse session stores raw HL7, patient, FHIR, and AI analysis at `app/api.py:1113-1128`. This may be required for the demo UI, but it is not governed by an output-field grant or protected-output policy. Explorer B called this out in `docs/agent-reports/next-hardening/02-endpoint-output-map.md:134`; the working tree adds tests only for message detail redaction at `tests/test_endpoint_governance.py:493-517`.

Concrete missing tests:

- Add read-endpoint policy tests for `/patients`, `/patients/{id}/timeline`, `/messages`, and `/oru/parse` preview, not only `/messages/{id}`.
- Add an explicit expected policy test for whether parse preview may return FHIR and identifiers by default; if allowed for demo, require a documented demo-mode gate and PHI-free audit.
- Add protected-output tests that prove `SECURITY_SHOW_PROTECTED_OUTPUT` is not a production authorization model.

### P2 - Note/text redaction is heuristic and not propagated as durable metadata

The new read-path redaction only treats an observation as note-like when `code == "note"` or the display contains `"note"`/`"clinical text"` at `app/api.py:250-258` and `app/patient_timeline.py:151-156`. SQLGuard removes `observations.value_raw` unless `note_read` is present at `app/sql_guard.py:69-71` and `app/sql_guard.py:285-294`, but there is no durable row-level note/taint metadata to distinguish string lab values from clinical prose. The only new endpoint test covers a literal `code="NOTE"` / `display="Clinical Note"` case at `tests/test_endpoint_governance.py:521-535`.

Bypass shape: a text OBX or legacy row with display such as `DISCHARGE_INSTRUCTIONS`, `NARRATIVE`, `COMMENT`, or another non-numeric clinical text label can flow through `/messages/{id}/observations`, patient timeline/context, and synthesis because the redaction decision is based on naming heuristics instead of ingestion-time note policy metadata.

Concrete missing tests:

- Ingest text-like OBX/NTE variants whose display does not contain `note`; assert every read path redacts or taints them.
- Add a persisted note/text classification field or side table and test that API, timeline, patient context, SQLGuard, and synthesis all consume the same metadata.
- Add regression coverage for legacy `value_raw` rows that predate the note policy.

### P3 - Safe-memory tests still mutate the shared default database

`tests/test_safe_memory.py` creates `db_path = str(tmp_path / "agent.db")` at line 14, but `commit_successful_turn` is called without a db path at lines 15-24 and the assertion explicitly reads `db_path="agent.db"` at line 27. This means the test writes to the shared working `agent.db`, which is already modified in the current tree. That can leave stale conversation state behind and make reference/memory tests order-dependent.

Concrete missing tests/fixes:

- Route safe-memory tests through an isolated DB path or monkeypatch the module DB path.
- Add cleanup around any test that writes known `conversation_id`/`session_id` rows.
- Add a guard test that no hardening tests write to the workspace `agent.db`.

## Residual Gaps From Explorer Reports

- `conversation_result_refs` remains schema-only; there is still no save/load/claim helper, TTL config, ownership check, or resolver test.
- `ContextBuilder` remains unwired from `/api/query`, so safe state and evidence tainting are not consistently represented as bounded context.
- `SECURITY_CONFIG` still lacks a result-reference TTL and broader retention namespace.
- Startup cleanup removes expired transient state, but there is no scheduled cleanup for long-running processes.
- Admin/reset and document reads remain outside the focused governance tests in this slice.

## Validation

No tests were run during this reviewer pass. This report is based on source inspection, current diffs, and the existing next-hardening reports.
