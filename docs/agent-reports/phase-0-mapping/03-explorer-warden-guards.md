# Agent Report: Explorer C - Warden And Guards

## Assignment

Map current Warden behavior, tool schemas, tokenization, SQL validation, calculator policy, audit JSONL, and PHI handling. No files edited.

## Files Inspected

- `app/warden.py`
- `app/healthcare_agent.py`
- `app/query_assistant.py`
- `app/security.py`
- `app/api.py`
- `app/db.py`
- `app/hl7_parser.py`
- `app/patient_timeline.py`
- `tests/test_e2e_warden.py`
- `tests/nist_verifier.py`
- `docs/security-kernel-plan.md`
- `warden_audit.jsonl`

## Current Flow

- Agent path opens `warden.request_scope()`, tokenizes question/history, validates LLM tool calls, deanonymizes string inputs before tools, tokenizes tool results before synthesis, then deanonymizes final answer/highlights.
- `PHITokenMap` is request-local and cleared on scope exit.
- `WardenAnalyzer` builds token maps by scanning the entire DB for full names, patient IDs, DOBs, and provider names.
- `WardenAnonymizer` performs recursive string/JSON tokenization and exact detokenization.
- `WardenPolicy` checks schema, blocked command tokens, then tool-specific policy.
- `WardenAuditLog` writes root `warden_audit.jsonl`.
- Tool schemas are hardcoded. Schema checking validates known fields if present but does not require required fields or reject extras.
- Warden validates `query_database` natural-language input; actual generated SQL is validated later by `query_assistant.validate_sql`.
- Calculator policy only whitelists `bmi` and `egfr`; implementation uses `values` while Warden schema expects `params`.
- PHI storage/read endpoints expose raw HL7, FHIR, patient identifiers, and timelines outside Warden gates.

## Risks / Bypasses

- Legacy fallback bypasses Warden.
- Current Warden has no `IntentGrant`, session binding, request ID, TTL, subject scope, allowed output fields, or grant-owned token records.
- Schema validation is not exact.
- `MODIFY` decisions are not applied as modified payloads.
- Calculator schema mismatch passes because missing required keys and extras are allowed.
- Generated SQL can escape Warden intent because later SQL validation lacks grant/table/column/output policy.
- PHI tokenization misses split first/last-name fields in DB results.
- Token restore can restore guessed/stale/user-injected/RAG-injected tokens if they match the request map.
- Every request maps the whole DB, not active subject/result scope.
- JSONL audit relies on convention, not enforced PHI-free validation.
- JSONL has no request/session IDs, retention model, or structured reason codes.
- HL7 NTE notes have no ingress taint/SQL-like note policy.
- Direct PHI endpoints and patient summaries are outside Warden gates.

## Recommended Implementation Notes

- Reuse Warden context ergonomics but change validation to `intercept(grant, tool, input, request_context)`.
- Replace hardcoded loose schemas with exact schemas.
- Introduce `IntentGrant` with session/request ID, subject, tools, tables/columns, output fields, row cap, expiry, and risk.
- Split responsibilities:
  - Warden v2: grant/tool/schema enforcement
  - SQLGuard: AST/allowlist/row/output policy
  - TokenGuard: scoped restore
  - CalculatorGuard: formula and parameter validation
  - AuditGuard: PHI-free event enforcement
- Restore tokens only for active request/grant and authorized final output fields.
- Tokenize structured PHI by field semantics, not only exact full-string replacement.
- Make `governance_events` canonical PHI-free audit; keep JSONL temporary/debug only.
- Remove or constrain `/api/query` fallback.
- Treat RAG chunks, HL7 notes, prior assistant text, and client JSON as tainted evidence only.

## Tests To Add

- Exact schema tests for missing/extra/wrong fields and nested types.
- Grant enforcement tests for missing/expired/wrong-session/disallowed tool/table/column.
- SQLGuard tests for blocked tables, unsafe constructs, no limits, note/raw columns, and missing predicates.
- TokenGuard tests for guessed, stale, wrong-session, RAG-injected, user-injected, and out-of-grant tokens.
- PHI tokenization tests for split names, DOB variants, patient IDs, provider fragments, raw HL7, and FHIR.
- Audit helper rejects/redacts PHI-bearing payload keys.
- No fallback path can call ungated `process_query`.
- HL7 note policy handles SQL-like NTE, prompt-injection NTE, and normal clinical NTE.
- Calculator exact params and clinical range tests.
- Protected read endpoints require output policies before PHI leaves server.

## Open Questions

- Should Warden v2 protect only `/api/query` first, or read/patient/timeline/message endpoints too?
- Is legacy `process_query` required?
- Should grant source be deterministic classifier, LLM gateway schema, endpoint-specific grant, or hybrid?
- Should demo cohort queries allow identifiers by default?
- Should raw HL7/FHIR ever be returned without protected-data grant?
- Should JSONL audit remain after `governance_events`?
