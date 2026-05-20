# Explorer A Report: Reference And Safe Memory Map

Date: 2026-05-20

Scope: read-only mapping for the Security Kernel hardening slice. This report covers safe memory, conversation state, result references, TTL/config, and current reference behavior. No behavior was intentionally implemented by Explorer A.

## Current Files And Functions

### Target Plan References

- `docs/security-kernel-plan.md`
  - Memory invariant: memory resolves references only; every turn still needs a fresh grant.
  - Ownership invariant: `conversation_id`, `parse_id`, `request_id`, result refs, and token records bind to the same `session_id`.
  - TTL defaults: demo sessions 8-24h, conversation state 30m, result refs 30m, HL7 parse sessions 10m, token records request-only.
  - Dynamic context: no raw history, prior assistant claims, notes, RAG chunks, or broad patient rows in pre-grant context.
- `docs/security-kernel-execution-plan.md`
  - Phase 3 calls for `conversation_states`, result refs, TTL, commit gate, ownership binding, and scope-jump tests.
  - Phase 4 adds bounded `ContextBuilder` context after memory is safe.
- `docs/agent-reports/phase-3-safe-memory/30-lead-safe-memory.md`
  - Existing residual work: deterministic pronoun/ordinal reference resolution, explicit scope-jump policy, cleanup for expired states/result refs.
  - Note: this report is stale on one point. `app/safe_memory.py` now reads conversation TTL from `SECURITY_CONFIG`.

### Safe Memory

- `app/safe_memory.py`
  - `conversation_id_for_session(session_id)`: deterministic `conv_{session_id}` mapping. Not exposed in current API response, but not opaque if it ever becomes client-visible.
  - `load_state(conversation_id, session_id)`: loads active, unexpired state through `db.get_conversation_state`.
  - `commit_successful_turn(conversation_id, session_id, agent_result)`: commits only after `success=True`, no `error`, and no `needs_clarification`.
  - Stored fields: `patient_ids`, `topic_codes`, `result_ids`, `scope`, `intent`, `expires_at`.
  - `extract_safe_metadata_from_tool_results(tool_results)`: recursively extracts `patient_id` values and `message_id` refs from tool result dictionaries.
  - `_assert_no_raw_memory(payload)`: blocks obvious raw-memory keys such as `answer`, `question`, `history`, `permissions`, and `admin`.
  - Current working-tree note: this file is modified and now uses `SECURITY_CONFIG["ttl"]["conversation_minutes"]`.

### Conversation State And Storage

- `app/db.py`
  - `init_db`: creates `demo_sessions`, `hl7_parse_sessions`, `conversation_states`, `conversation_result_refs`, `ai_interactions`, and `governance_events`.
  - Indexes exist for session/TTL lookups:
    - `idx_demo_sessions_expires_at`
    - `idx_hl7_parse_sessions_session_expiry`
    - `idx_hl7_parse_sessions_status_expiry`
    - `idx_conversation_states_session`
    - `idx_conversation_states_expires_at`
    - `idx_conversation_result_refs_session`
    - `idx_conversation_result_refs_expires_at`
  - `upsert_conversation_state`: inserts or replaces one active state row by `conversation_id`.
  - `get_conversation_state`: checks `conversation_id`, `session_id`, `status='active'`, and `expires_at > now`.
  - `cleanup_expired_security_state`: current working-tree helper deletes expired rows from `hl7_parse_sessions`, `conversation_states`, `conversation_result_refs`, and `demo_sessions`; it is called on API startup.
  - No helpers currently save/load/claim `conversation_result_refs`; the table is schema-only.
  - No background/scheduled reconciler exists beyond startup cleanup.

### Sessions And TTL Config

- `app/security_validation.py`
  - `SECURITY_CONFIG["ttl"]` has:
    - `demo_session_hours`, default `12`
    - `hl7_parse_minutes`, default `10`
    - `conversation_minutes`, default `30`
  - `SECURITY_CONFIG["timeouts"]` covers LLM, SQL, HL7 parse, RAG, and request timeouts.
  - Current working-tree note: `SECURITY_CONFIG["debug"]` was added with `show_sql_used` and `show_protected_output`.
  - Missing from config relative to target: `result_reference_minutes`, `retention`, explicit strictness/local-vs-production posture beyond `deployment.mode`.
- `get_or_create_demo_session(request, response)`
  - Accepts `demo_session_id` cookie or `X-Session-Id` only if `get_demo_session` finds an unexpired server-known row.
  - Creates/refreshed session rows and sets an HttpOnly `SameSite=Lax` cookie.

### Query Endpoint Memory Flow

- `app/api.py`
  - `/api/query` creates `request_id`, gets/creates `session_id`, derives `conversation_id`, and loads `prior_state`.
  - Current working-tree state imports `resolve_safe_references`, resolves `req.question` against `prior_state`, audits `api.query.references`, and fails closed with deny/clarify responses before intent classification when needed.
  - `classification` now receives `governed_question`; `build_query_grant` receives `subject=resolution.subject`; `run_agent_query` receives `governed_question`.
  - Agent execution is wrapped in a request timeout helper; timeout returns failure and does not reach the memory commit path.
  - `ContextBuilder` is still not wired into this endpoint.
  - After a successful agent response, `commit_successful_turn` commits typed metadata and emits `api.query.memory` audit.

### Current Reference Behavior

- `app/healthcare_agent.py`
  - `_run_standard` tokenizes current question and client-supplied `history` through Warden before planning.
  - `_plan` sends the last five history messages to the planner and tells it to interpret pronouns against the immediately preceding message.
  - `_tool_query_database` passes the tokenized history to `generate_sql_from_question`.
  - Even with the new API-level safe-state resolver, downstream planning and SQL generation still retain history-driven reference instructions.
- `app/query_assistant.py`
  - SQL prompt rule 12 explicitly tells the SQL generator to use chat history and previous assistant answers to resolve pronouns and implicit context.
  - `generate_sql_from_question(question, history)` includes the supplied history JSON directly in the SQL-generation prompt.
  - `process_query(question, history)` remains a legacy entrypoint and also uses raw caller-supplied history. `/api/query` no longer falls back to it, but tests/scripts still import it.
- `app/context_builder.py`
  - `pre_grant` summarizes state using counts and topic/scope, not raw IDs.
  - `planning` includes grant summary and safe state summary.
  - `synthesis` sanitizes authority keys from tool/RAG evidence.
  - Not currently wired into `/api/query` or `HealthcareAgent`.
- `app/reference_resolver.py`
  - Present as an untracked working-tree file and currently wired from the modified `app/api.py`.
  - Defines `ReferenceResolution` and `resolve_safe_references(question, state)`.
  - Handles pronouns/simple phrases (`that patient`, `his`, `her`, `first one`, etc.), single-patient narrowing, ambiguous multi-patient clarification, and some export/identifier scope-jump denial.
  - Resolution currently appends `[Resolved safe reference: patient_id=...]` to the natural-language question.

### Result References

- Current committed memory stores `result_ids` inside `conversation_states` as strings such as `message:7`.
- `conversation_result_refs` exists in schema and indexes, but no application code writes or reads it.
- Result refs therefore do not currently have independent TTL, status, lookup helper, session check, or bounded payload.
- `ContextBuilder.pre_grant` exposes only `result_ref_count`; nothing resolves or dereferences a result ref today.

## Gaps Against The Plan

- Deterministic reference resolution is now partially wired into the working tree, but it is untracked/untested in the files inspected here and still needs hardening before it should be considered complete.
- Prior assistant text can still influence planning and SQL generation through `req.history`; this conflicts with the target rule that prior assistant claims cannot grant authority or mutate/resolve memory.
- `ContextBuilder` exists and has tests, but it is not integrated into the query pipeline.
- Safe state now affects reference resolution and grant subject in the working tree, but `topic_codes`, `result_ids`, and richer state are still not used in a bounded context flow.
- Result refs are schema-only. There is no lifecycle, resolver, TTL config, ownership helper, or fail-closed use path.
- `SafeConversationState.intent` is hard-coded to `clinical_query` during commits, even when tools imply guideline reference or calculation behavior.
- `SafeConversationState.scope` is inferred from tools, not from the grant/classification. `query_database` always maps to `cohort`, so a single-patient SQL query can be stored as cohort.
- `conversation_id_for_session` is deterministic. This is probably fine while server-internal, but should not become a client-visible opaque pointer without review.
- Startup cleanup now deletes expired transient state, but there is still no scheduled/background reconciler and no protected trace retention cleanup.
- `SECURITY_CONFIG` still lacks the planned `retention` namespace and result-reference TTL.
- Existing memory tests touch the default `agent.db` despite creating a `tmp_path`; this is risky in a shared working tree.
- `reference_resolver.py` appends `[Resolved safe reference: patient_id=...]` to the natural-language question. Decide whether that patient ID should instead be carried only as structured server-owned metadata/grant subject rather than text sent through LLM prompts.

## Exact Tests Needed

### Reference Resolver Unit Tests

- `test_no_reference_returns_unchanged_without_state`
- `test_single_patient_pronoun_resolves_to_subject`
- `test_single_patient_that_patient_resolves_to_subject`
- `test_first_second_third_one_resolve_by_order`
- `test_ordinal_out_of_range_requires_clarification`
- `test_multi_patient_pronoun_requires_clarification`
- `test_reference_without_state_requires_clarification`
- `test_export_reference_scope_jump_denied`
- `test_identifier_reference_scope_jump_denied_for_non_single_patient_state`
- `test_single_patient_to_cohort_scope_jump_requires_clarification`
- `test_resolver_does_not_use_raw_history_or_assistant_text`

### `/api/query` Integration Tests

- `test_api_query_passes_safe_state_to_reference_resolver_before_grant`
- `test_api_query_denies_reference_scope_jump_before_agent_runs`
- `test_api_query_clarifies_ambiguous_reference_before_agent_runs`
- `test_api_query_resolved_subject_is_bound_to_grant_or_structured_context`
- `test_api_query_uses_governed_question_for_classifier_and_agent`
- `test_api_query_timeout_returns_no_memory_commit`
- `test_api_query_does_not_send_prior_assistant_claims_as_authority`
- `test_api_query_failed_agent_does_not_commit_memory`
- `test_api_query_timeout_or_exception_does_not_commit_memory`
- `test_api_query_denied_intent_does_not_commit_memory`
- `test_api_query_clarification_does_not_commit_memory`
- `test_api_query_success_commits_only_typed_metadata`

### Result Ref Tests

- `test_result_ref_saved_with_session_owner_and_ttl`
- `test_result_ref_lookup_requires_same_session`
- `test_result_ref_lookup_rejects_expired_ref`
- `test_result_ref_lookup_rejects_unknown_or_guessed_ref`
- `test_result_ref_payload_is_bounded_and_not_authority`
- `test_conversation_state_result_ids_cannot_be_used_without_live_result_ref`
- `test_result_reference_ttl_uses_security_config`

### Config And Cleanup Tests

- `test_security_config_has_result_reference_ttl_and_retention_namespace`
- `test_conversation_ttl_uses_security_config`
- `test_expired_conversation_state_unusable`
- `test_expired_parse_session_unusable`
- `test_cleanup_expires_conversation_states_and_result_refs_without_resuming_work`
- `test_startup_cleanup_deletes_only_expired_transient_security_state`
- `test_get_or_create_demo_session_rejects_unknown_client_supplied_session_id`

### Regression/Static Tests

- `test_context_builder_not_authority_source`
- `test_no_raw_question_history_answer_in_conversation_state`
- `test_no_low_level_llm_imports_outside_gateway`
- `test_no_legacy_process_query_fallback_from_api_query`
- `test_reference_resolution_runs_before_agent_tool_execution`
- `test_safe_memory_tests_use_isolated_db_not_default_agent_db`

## Integration Cautions

- Coordinate with the owner of the current uncommitted changes before editing `app/safe_memory.py`, `app/security_validation.py`, or `app/reference_resolver.py`.
- Also coordinate before editing the currently modified `app/api.py`, `app/db.py`, `app/healthcare_agent.py`, or `app/warden.py`.
- Avoid carrying reference authority by appending authority text to the user question if a structured grant subject or resolver output can carry the subject. Text injection is easier for downstream LLM prompts to reinterpret.
- If `req.history` remains for UX continuity, treat it as tainted display context only. It should not resolve subjects, broaden scope, authorize output, or commit memory.
- Result refs need a clear model before use: either keep `message:<id>` as a durable clinical object pointer with fresh read grants, or add first-class `conversation_result_refs` rows with separate TTL/status/payload. Mixing both without rules will be confusing.
- A resolved reference must narrow only; it must not expand from single-patient state to cohort/export/admin/identifier output.
- Memory commit should probably use grant/classification metadata for `intent` and `scope`, not just tool names.
- Be careful running existing tests in the shared workspace. Some tests currently write to `agent.db`, and `agent.db` is already modified in the working tree.
- This report did not run validation tests because the requested task was read-only mapping plus report creation.
