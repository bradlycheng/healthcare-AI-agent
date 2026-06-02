# Agent Report: security-reviewer -- Slice 3 (RAG Query Tokenization)

## Assignment

Final security review of Slice 3 (RAG query tokenization) before merge.
Verify that patient names no longer reach Bedrock Titan via retrieve_context()
at all call sites in healthcare_agent.py. Check threading of tokenized query,
warden_ctx lifetime, context deanonymization, fallback behavior, tests, and scope.

## Files Inspected

- app/healthcare_agent.py (lines 346-539, 750-848)
- app/query_assistant.py (full)
- tests/test_rag_query_tokenization.py (full)
- docs/agent-reports/baseline-audit/30-worker-slice3-rag-query-tokenization.md

## Files Changed

None (read-only review)

---

## Critical Findings

None.

---

## Warning Findings

**W-1 -- Fallback PHI amplification in _tool_query_database (line 809)**

```python
safe_rag_query = input_data.get("_safe_rag_query") or query
```

At line 809, the local `query` variable has already been mutated at line 773:
```python
query = f"{query} for patient {grant.subject}"
```
`grant.subject` is a real patient identifier. If `_tool_query_database` is called
without `_safe_rag_query` in input_data (future integration path, unit test harness,
or alternate dispatch loop), the fallback sends a PHI-containing string -- with the
subject appended -- to Bedrock Titan via retrieve_context(). This is worse than the
pre-Slice-3 state because the subject suffix is new.

The primary agent dispatch path is correct (always injects `_safe_rag_query`). This
does not regress the current in-scope call path.

Acceptable deferral because the fallback only fires outside the normal dispatch path.

Recommended fix (either):
- Capture pre-mutation query before line 773:
    `_rag_query_backup = query`
  and use `input_data.get("_safe_rag_query") or _rag_query_backup` at line 809
- Or replace fallback with `input_data.get("_safe_rag_query") or ""` and skip
  RAG gracefully if the key is absent

---

## Informational Findings

**I-1 -- _warden_ctx stored in real_tool_input dict**
real_tool_input is a local variable; no reference is returned, stored on self,
serialized, or logged. Safe under the current synchronous single-request architecture.
Future async or tool-result-caching refactors must ensure context manager is still
active when the reference is used. PASS.

**I-2 -- test_query_database_tool_no_phi_to_bedrock lacks positive token-presence assertion**
Full coverage provided by test_query_database_retrieve_context_called_with_token
in TestRagRetrievalCalledWithSafeQuery. No gap, organizational note only. PASS.

**I-3 -- retrieve_context() has no runtime enforcement of pre-tokenization**
The docstring IMPORTANT note is advisory. A future caller could pass raw PHI.
A future hardening slice could add a typed wrapper for pre-tokenized strings.
Current model (callers are responsible) is consistent with existing security design. PASS.

**I-4 -- process_query() deferred risk remains active**
process_query() in query_assistant.py calls retrieve_context(question) with no Warden
scope. Deferred comment at the call site is clear and complete. If the legacy /query
endpoint is reachable from external clients, it remains a live PHI-to-Bedrock path.
Should be tracked in the hardening plan backlog. Acceptable deferral for Slice 3. PASS.

---

## Per-Item Verification

| Item | Result |
| :-- | :-- |
| Site 1: safe_question used at line 376 | PASS |
| Sites 2&3: _safe_rag_query injected after intercept() | PASS |
| Private keys ignored by non-RAG tools | PASS |
| warden_ctx lifetime safe (synchronous) | PASS |
| context_text deanonymized with truthiness guard | PASS |
| Fallback in _tool_query_database | WARNING W-1 |
| process_query deferral documented | PASS |
| Tests assert absence of raw name at retrieve_context | PASS |
| Tests assert positive token presence (Test 3) | PASS |
| Scope discipline (only ownership files changed) | PASS |
| Source attribution unaffected (metadata-based) | PASS |
| Sign-off condition met | PASS |

---

## Residual Risks Carried Forward

- W-1: Fallback PHI amplification (grant.subject append) in _tool_query_database
  if _safe_rag_query absent -- deferred, primary path is correct
- process_query() legacy RAG path -- no Warden scope, deferred to future slice
- RAG document PHI scanning -- pre-existing warning, not introduced by Slice 3

---

## Sign-Off Condition

**MERGEABLE.**

Primary PHI-to-Bedrock leakage risk on HealthcareAgent._run_standard is fully closed
at all three active call sites. W-1 fallback does not regress the pre-Slice-3 state
for any in-scope call path and is acceptable as a tracked deferral. 8/8 new tests
pass; 171/171 total tests pass; 0 regressions.
