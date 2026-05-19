# Agent Report: Explorer A - Query Flow

## Assignment

Map `/api/query`, `process_query`, agent tool calls, SQL generation, RAG usage, fallback paths, and direct low-level LLM calls. No files edited.

## Files Inspected

- `app/api.py`
- `app/healthcare_agent.py`
- `app/query_assistant.py`
- `app/warden.py`
- `app/llm_client.py`
- `app/vector_store.py`
- `app/embeddings.py`
- `app/patient_timeline.py`
- `tests/test_e2e_warden.py`

## Current Flow

- `/api/query` rate-limits by IP, blocks obvious injection patterns, then calls `run_agent_query(req.question, req.history, depth=req.reasoning_depth)`.
- `run_agent_query` constructs `HealthcareAgent`, registers `query_database`, `search_guidelines`, `get_patient_context`, `clinical_calculator`, and `ask_clarification`.
- Standard agent flow opens a Warden request scope, anonymizes question/history, calls planner LLM with `call_llm_for_json`, validates proposed tools through `warden_ctx.intercept`, deanonymizes tool inputs, executes tools, tokenizes tool results, calls synthesis LLM, then deanonymizes final answer.
- `query_database` calls `generate_sql_from_question`, `validate_sql`, `execute_safe_query`, and `retrieve_context`.
- RAG uses `retrieve_context` -> `vector_store.search` -> `embeddings.embed_text`, which calls Bedrock Titan directly.
- Legacy fallback is still active: if the agent returns failure or raises, `/api/query` calls `process_query(sanitize_text(req.question), req.history)`.
- `process_query` performs its own LLM SQL generation, SQL validation/execution, RAG retrieval, and formatting without Warden.

## Risks / Bypasses

- `/api/query` can bypass any future kernel through the legacy fallback to `process_query`.
- SQL generation in the main agent happens after deanonymization, so the SQL LLM can see real PHI.
- Legacy `process_query` sends raw/sanitized question, raw history, DB results, and RAG context to LLM calls without Warden tokenization.
- Deep mode sends raw question to a reflection LLM before Warden, then prepends LLM-generated strategy into the governed request.
- RAG embeddings call Bedrock directly with query text outside Warden/gateway control.
- Warden `MODIFY` decisions are not applied; caller only checks `DENY`.
- Warden schema validation is not exact: missing required fields and extra fields are allowed.
- `clinical_calculator` schema expects `params`, while the agent implementation uses `values`.
- SQL validation is syntactic safety, not authorization. It lacks table allowlists, column allowlists, required limits, row caps, and grant predicates.
- `patient_timeline.generate_journey_summary` is another direct PHI-to-LLM path.

## Recommended Implementation Notes

- Make the kernel/gateway the only callable path from `/api/query`.
- Remove legacy fallback or route it through the same kernel controls.
- Centralize all LLM and embedding calls behind `llm_gateway.py`.
- Keep SQL generation tokenized; restore/deanonymize only after Warden/SQLGuard validation and immediately before read-only execution.
- Treat LLM plans, reflection output, generated SQL, and RAG chunks as untrusted evidence.
- Apply Warden `MODIFY` results or fail closed on any non-`ALLOW` decision.
- Make tool schemas exact: required keys, no extras, bounded strings, enums, and aligned calculator parameters.
- Route RAG through gateway/guard logic with PHI handling and poisoned-content checks.

## Tests To Add

- Agent failure must not call ungated `process_query`.
- SQL generation LLM must receive tokenized input, not real patient names/DOBs/IDs.
- Deep mode reflection must run through gateway/Warden or be disabled.
- RAG embedding calls must be gateway-mediated and PHI-controlled.
- Warden `MODIFY` decisions must truncate/modify or deny before execution.
- Legacy query path, if retained, must enforce Warden tokenization and table/column policy.
- Generated SQL reading blocked tables, missing limits, or disallowed columns must be rejected.
- Static boundary test: no direct `llm_client` or `embeddings` calls outside allowed gateway modules.

## Open Questions

- Should legacy `process_query` be removed entirely, or retained only behind a kernel-controlled compatibility flag?
- Should deep mode be disabled until reflection is gateway-mediated?
- What table/column allowlist should Phase 1 enforce by default?
- Should `/api/query` return `sql_used` only in debug/protected mode?
