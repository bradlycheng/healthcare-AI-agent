# Worker Report: Slice 3 -- RAG Query Tokenization

**Date:** 2026-06-02
**Agent:** narrow-worker (Slice 3)
**Model:** claude-sonnet-4-6
**Slice:** Slice 3 of docs/agent-reports/baseline-audit/00-lead-hardening-plan.md

---

## Risk Addressed

Security-explorer finding C1: `retrieve_context(question)` was called with the
raw (un-tokenized) user question at three call sites in `healthcare_agent.py` and
one legacy call site in `query_assistant.py`. Because `retrieve_context` calls
`embed_text()` which calls Bedrock Titan for embedding, any patient name present in
the question was sent to Bedrock in cleartext, bypassing the Warden IN-GATE.

---

## Files Changed

| File | Change |
| :--- | :--- |
| `app/healthcare_agent.py` | Fix Sites 1, 2, 3; thread `_safe_rag_query` and `_warden_ctx` |
| `app/query_assistant.py` | Add docstring to `retrieve_context()`; add deferred comment at Site 4 |
| `tests/test_rag_query_tokenization.py` | New test file (8 tests) |

---

## Code Changes Detail

### Site 1 — Direct-answer path (`_run_standard` line 374)

**Before:**
```python
_, direct_sources = retrieve_context(question)
```

**After:**
```python
# IN-GATE: use the Warden-tokenized question so no raw PHI is sent
# to Bedrock Titan for embedding (Slice 3 fix -- Site 1).
_, direct_sources = retrieve_context(safe_question)
```

`safe_question` is the Warden-anonymized version of the question, computed 5 lines
earlier at line 352. No structural change needed.

---

### Sites 2 & 3 — Dispatch loop threading

The core fix for the tool functions: after building `real_tool_input`
(deanonymized, for DB queries), a private `_safe_rag_query` key is added using
the original `tool_input["query"]` (still tokenized, before deanonymization).
A `_warden_ctx` reference is also added for use in context deanonymization.

These keys are added **after** the Warden schema check (`warden_ctx.intercept`),
so they do not trigger the strict `TOOL_SCHEMAS` validator.

```python
# Slice 3 -- RAG Query Tokenization: thread the pre-tokenized
# query and Warden context into real_tool_input under private keys
# so tool functions can pass safe text to retrieve_context()
# (which calls embed_text() / Bedrock Titan) instead of raw PHI.
# These keys are added AFTER the Warden schema check so they do
# not trigger the strict schema validator.
if "query" in tool_input:
    real_tool_input["_safe_rag_query"] = tool_input["query"]
real_tool_input["_warden_ctx"] = warden_ctx
```

### Site 2 — `_tool_query_database`

```python
# Slice 3 fix (Site 2): use the Warden-tokenized query for embedding
safe_rag_query = input_data.get("_safe_rag_query") or query
context_text, sources = retrieve_context(safe_rag_query)

# OUT-GATE: deanonymize any PHI tokens in retrieved context
warden_ctx = input_data.get("_warden_ctx")
if warden_ctx is not None and context_text:
    context_text = warden_ctx.deanonymize(context_text)
```

The deanonymized `query` (real patient name) is still used for SQL generation
unchanged — only the RAG call changes.

### Site 3 — `_tool_search_guidelines`

Same pattern as Site 2: `_safe_rag_query` for the RAG call, `_warden_ctx` for
deanonymizing the returned context text.

---

### Site 4 — `query_assistant.process_query()` (deferred)

`process_query()` is a legacy function with no Warden scope. Adding a Warden
`request_scope` to it would require significant refactoring (grant construction,
PHI token map seeding) that is out of scope for Slice 3.

A comment was added at the call site:

```python
# DEFERRED (Slice 3): process_query() is a legacy function with no Warden scope.
# retrieve_context() is called here with the raw question, which means any patient
# name in the question is sent to Bedrock Titan for embedding without tokenization.
# Fixing this requires adding a Warden request_scope to process_query(), which is a
# larger refactor deferred to a future hardening slice.  The primary clinical query
# path in healthcare_agent.py (HealthcareAgent._run_standard) is already fixed.
```

The `process_query()` path is used by the legacy `/query` flow via
`query_assistant.py`, which is separate from the primary `HealthcareAgent` path
used by the Streamlit UI and `/agent/query` API endpoint.

---

### `retrieve_context()` docstring

Added an IMPORTANT note to `retrieve_context()` in `query_assistant.py`:

```
IMPORTANT: The question parameter must be pre-tokenized (Warden-anonymized) when
called from a Warden-active context.  Raw PHI in the question will be forwarded to
embed_text() and then to Bedrock Titan for embedding -- bypassing the Warden IN-GATE.
See healthcare_agent.py for the correct call pattern.
```

No signature change. No retrieval logic change. Source attribution unchanged.

---

## Architecture Note: `anonymize_json` re-tokenization

The dispatch loop (lines 511-520) calls `warden_ctx.anonymize_json(tr.result)`
on each tool result before passing it to `_synthesize`. This re-tokenizes any
real names in the tool result dict (including the deanonymized `context_text`)
before the LLM sees it during synthesis. This is correct — the synthesis LLM
should only see tokens, not real PHI.

The OUT-GATE (`warden_ctx.deanonymize(answer)`) then restores tokens in the
LLM's answer for the end user.

The deanonymize call in the tool functions (`warden_ctx.deanonymize(context_text)`)
ensures the tool result dict has clean (real-name) content when first formed —
important for any non-synthesis use of the result dict (e.g., source attribution,
direct inspection, future tool-result caching).

---

## Tests

File: `tests/test_rag_query_tokenization.py`
8 tests in 3 test classes.

### TestRagQueryNoPhiToBedrock (3 tests)

Verifies that `retrieve_context()` is called with a tokenized query (not raw
patient name) in all three call paths: direct-answer, `search_guidelines` tool,
`query_database` tool.

Mocking strategy: `app.query_assistant.retrieve_context` patched to capture the
argument; `app.warden.WardenAnalyzer.build_token_map` patched to seed a known
`real_name <-> phi_token` mapping; `agent_planning` returns a plan with the
PHI token in the query field (simulating LLM output after seeing `safe_question`).

### TestRagContextDeanonymizedBeforeReturn (2 tests)

Verifies that when `retrieve_context()` returns `context_text` containing a PHI
token, the token is replaced (deanonymized) in the tool's result dict before the
dispatch loop's `anonymize_json` step.

- `test_search_guidelines_context_deanonymized`: patches `_run_standard` to capture
  the raw tool result before `anonymize_json`; asserts no raw token in result.
- `test_query_database_context_deanonymized`: directly calls `_tool_query_database`
  with a controlled `input_data` dict including real `_warden_ctx` and `_safe_rag_query`.

### TestRagRetrievalCalledWithSafeQuery (3 tests)

Positive assertions: verifies that the PHI token appears in the `retrieve_context`
query argument (confirming the tokenized form is used), not the real patient name.
Covers `search_guidelines`, `query_database`, and the direct-answer path.

---

## Constraints Met

- `retrieve_context()` signature: unchanged
- RAG chunk retrieval logic: unchanged
- Source attribution (`sources` list): unchanged
- `run_oru_pipeline()` and HL7 pipeline: not touched
- `app/vector_store.py`, `app/embeddings.py`, `app/warden.py`,
  `app/llm_gateway.py`, `app/security_validation.py`, `app/alerts.py`,
  `app/agent.py`: not touched

---

## Residual Risks / Deferred Items

1. **`process_query()` RAG embedding (DEFERRED):** The legacy `process_query()`
   function in `query_assistant.py` calls `retrieve_context(question)` with the
   raw question (no Warden scope). The primary agent path is fixed; this legacy
   path is deferred to a future hardening slice. Documented at the call site
   with a clear DEFERRED comment.

2. **RAG document PHI scanning (pre-existing WARNING):** Clinical reference
   documents in `docs/` are not scanned for PHI before indexing. If a document
   contains a patient name, it could appear in RAG `context_text` chunks.
   The `warden_ctx.deanonymize` call in the tool functions would replace known
   tokens, but names not yet in the token map would pass through. This is a
   separate risk from the embedding PHI leakage fixed here.

3. **`anonymize_json` re-tokenizes deanonymized context:** The dispatch loop
   re-tokenizes tool results before synthesis. The deanonymized `context_text` is
   re-tokenized before the LLM synthesis step. This is correct behavior (LLM
   should not see PHI) but means the context in the synthesis prompt still
   contains tokens. The final answer is restored by the OUT-GATE. No action
   needed — this is by design.

---

## Sign-Off Condition

Patient name in a clinical query does NOT appear in the string passed to
`embed_text()` via `retrieve_context()` — verified by 3 tests that patch
`app.query_assistant.retrieve_context` and assert the captured argument contains
no raw patient name. Source attribution continues to return correct file references
(unchanged). 8/8 new tests pass. 171/171 total tests pass.
