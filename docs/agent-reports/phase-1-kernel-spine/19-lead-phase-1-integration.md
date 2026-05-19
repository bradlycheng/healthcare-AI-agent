# Lead Integration Report: Phase 1 Kernel Spine

## Summary

Phase 1 kernel spine is implemented. This slice closes the highest-risk bypasses first: ungated query fallback, client-authoritative `/messages`, direct low-level LLM imports, missing Warden grants, and lack of canonical governance audit storage.

## Key Changes

- Added security contracts/config/audit/session helpers.
- Added `governance_events`, `demo_sessions`, `hl7_parse_sessions`, `conversation_states`, `conversation_result_refs`, and `ai_interactions` tables.
- Added `llm_gateway.py` as the low-level LLM boundary.
- Migrated direct LLM callers through gateway wrappers.
- Removed `/api/query` legacy fallback behavior.
- Added grant-aware Warden request scopes and exact schema validation.
- Added `/oru/parse` parse-session creation.
- Added `/messages` parse-session persistence gate.
- Disabled direct ORU persistence by default; `/oru/parse` must preview and issue a `parse_id` before `/messages` persists.
- Added one-time parse-session claim before save to prevent parse replay.
- Added Warden grant-expiry enforcement.
- Added PHI-free governance audit events for read endpoints that expose patient/message data.
- Minimized patient journey summary prompts by withholding direct identifiers.
- Added configurable HL7 parse timeout enforcement.

## Tests Run

```text
pytest tests/test_security_kernel_phase1.py -q
pytest tests/test_e2e_warden.py -q
pytest tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
```

Combined gate:

```text
35 passed
```

## Known Residual Work

- Update frontend save flow to send `parse_id`.
- Add full SQLGuard AST/allowlist/depth.
- Add full Hl7Guard note policy and malformed-message limits.
- Add TokenGuard scoped restore gate.
- Add RAG trust filtering and embedding governance.
- Add safe memory commit gate.
- Add runtime timeout enforcement to all LLM/RAG/SQL paths beyond the Phase 1 HL7 parse timeout.
- Replace Phase 1 broad/internal query grant with deterministic intent-to-grant mapping.
- Add stricter output gating for read endpoints in the future user/RBAC slice.

## Gate Result

Phase 1 kernel spine passed the focused test gate after reviewer-blocking fixes. Remaining items are Phase 2/3 guard depth or deferred RBAC/UI compatibility work.
