# Security Kernel and Warden v2 Plan

## Summary

Build a kernel-first governance layer for the healthcare AI agent. Warden v2 becomes the grant-based tool enforcement layer inside the kernel, while separate guards own SQL, HL7, token restore, metadata provenance, calculators, RAG trust, memory commits, and interruption cleanup.

This document describes the finished V2 target architecture. Rollout sequencing and temporary implementation phases live in `docs/security-kernel-execution-plan.md`.

## Non-Negotiable Invariants

- Every sensitive action requires a session context, a server-owned grant, exact schema validation, guard decision metadata, PHI-free audit, and fail-closed behavior.
- Untrusted data can provide facts, never authority. Client JSON, HL7 notes, RAG chunks, LLM output, and prior assistant text cannot create grants, parse validation status, RAG trust, token ownership, output authorization, or memory commits.
- A crash leaves either no committed effect or a complete server-owned transaction. Incomplete requests/sessions are reconciled as interrupted or expired, not resumed.
- Memory resolves references only. Every turn still gets a fresh grant.
- PHI release happens only through TokenGuard at final output.

## Hardening Decisions

- Use server-issued `session_id` as the v1 demo ownership boundary. Reserve nullable `actor_id` for future authenticated users, but do not build full user/RBAC auth in this kernel slice.
- Bind `conversation_id`, `parse_id`, `request_id`, result refs, and token records to the same `session_id`. A caller can use only objects owned by the same session and still within TTL.
- Keep full user/admin/RBAC auth out of the first kernel slice. Password-protect reset/admin for now, and never allow reset/delete/admin actions through chat or LLM delegation.
- Keep `ai_interactions` for governance/debugging, but classify it as PHI-bearing protected trace data, not PHI-free audit and not live authorization state. Add retention limits and access restrictions.
- Scope TokenGuard maps to the active grant/request. Do not build broad restore authority from the entire database.
- Make SQL safety more than AST validation: enforce tables, columns, subject predicates, output fields, row caps, aggregate-vs-identifier rules, and note-column policy.
- Apply note policy twice: deny unsafe SQL-like notes at HL7 ingestion, and treat any retrieved stored note as tainted evidence only.
- Bound canonicalization decoding. Decoded payloads are evidence, not replacement truth, and recursive decoding must have depth/size limits.
- Require strict schemas for every LLM Gateway task. Reject extra fields and ignore any LLM-proposed grants, output authorization, trust levels, or policy overrides.
- Rename "recovery job" to "interruption reconciler" or "incomplete cleanup"; it marks stale/incomplete work unusable instead of resuming it.
- Treat legacy stored notes/messages as tainted at retrieval because they may predate new ingress policy.
- Add idempotency for HL7 saves using parse ID, raw HL7 hash, and/or request ID so retries do not duplicate messages unexpectedly.
- Define safe external errors and detailed internal reason codes. User responses must not include raw HL7, PHI, token maps, stack traces, or detection-rule details.
- Use `governance_events` as the canonical PHI-free kernel audit trail. Keep Warden JSONL only as temporary compatibility/debug output during migration. No security decision may depend on JSONL logs.
- Defer production CORS/CSRF hardening, but do not write kernel code that assumes permissive CORS or unauthenticated sessions are safe for production.
- Client-supplied clinical JSON is never authoritative. Prefer strict rejection of legacy `/messages` clinical JSON; accept a short transition only if needed to keep the current UI functional, while recomputing or ignoring those fields server-side.
- Use stateful server-side records for session, parse, result, and conversation ownership. Client-visible IDs are pointers, not authority. Defer stateless signed tokens unless a later cross-service or lightweight-link use case needs them.
- Include structural guardrails in the final design: a PHI-safe audit helper, central `SECURITY_CONFIG`, schema/migration version marker, safe output escaping helper, minimal required RAG metadata, env-configured admin password, and invariant tests.

## Key Interfaces

- `CanonicalInput`: raw-present flag, normalized value, input kind, language, decoded payload summaries, warnings, taint labels, reject reason.
- `IntentGrant`: intent, risk, `session_id`, optional future `actor_id`, scope, subject, allowed tools, allowed tables/columns, output fields, max rows, expiry.
- `SecurityDecision`: allow/deny/clarify, reason, evidence categories, guard name, audit-safe payload.
- `SafeConversationState`: typed patient/result/topic/scope metadata with 30-minute TTL.
- `TokenRecord`: request ID, token, field type, source, output authorization, in-memory real value.
- `Hl7ParseSession`: parse ID, `session_id`, optional future `actor_id`, raw HL7 hash, status, parse result, note policy result, expiry.
- `DemoSession`: server-issued opaque session ID, created time, last-seen time, expiry, optional auth context placeholder.

## Endpoint Behavior

- Session ownership: v1 uses server-issued opaque `session_id`, preferably in an HttpOnly cookie. For non-browser/demo clients, `X-Session-Id` may be accepted only if server-issued and known. Clients must not choose arbitrary session IDs.
- `/api/query`: canonicalize, load safe state, classify through gateway, build grant, resolve references, plan tools, validate via Warden v2, execute guarded tools, synthesize through gateway, restore/redact through TokenGuard, commit state only after approved success.
- `/oru/parse`: canonicalize HL7 while preserving structure, validate ORU/PID/OBR/OBX shape, enforce note ingress policy, deterministically parse, server-build FHIR, optionally run schema-bound extraction, create validated parse session for preview or persist server-owned result.
- `/messages`: accept `parse_id` or raw HL7 only. Persist only validated server-owned parse results. Reject client-supplied patient, observations, summary, FHIR, status, trust, and authorization fields by default. If transition compatibility is needed, accept only while recomputing/ignoring clinical fields server-side.
- Read endpoints: validate path/query fields, build read grants, enforce output-field policy, escape/render safely, audit PHI-free decisions.
- Admin endpoints: password-protected direct reset/admin calls only in this slice. They cannot be invoked, planned, or delegated through chat, RAG, HL7 notes, LLM output, or agent tools. Approved admin calls still emit explicit admin grant/audit metadata.

## Dynamic Context Rules

- Do not send raw history, raw notes, RAG chunks, prior assistant claims, or broad patient rows into pre-grant context.
- Context may narrow or explain a request, but it cannot expand authority.
- Planning context must never contain material that can grant tools, alter policy, authorize output fields, or mutate memory.
- Synthesis context may include richer material only after tool execution and only within the active grant.
- Dynamic context implementation must emit context-source metadata and must be covered by prompt-injection, metadata-injection, and scope-jump tests.

## Session And TTL Defaults

- Demo session TTL: 8-24 hours, refreshed on safe activity.
- Conversation state TTL: 30 minutes.
- Result reference TTL: 30 minutes.
- HL7 parse session TTL: 10 minutes.
- Token records: current request lifetime only, memory-only.
- All governed objects must check same `session_id`, valid status, and unexpired TTL before use.
- Client-visible IDs such as `parse_id`, `conversation_id`, and `result_id` are opaque pointers to server-side records. They do not carry status, trust, authorization, or clinical authority.

## Error, Legacy Data, And Idempotency Defaults

- User-facing errors are safe and generic; internal reason codes are specific and audit-safe.
- Legacy stored notes are always treated as tainted clinical text at retrieval, even if they were stored before note ingress policy existed.
- HL7 save operations must be idempotent or duplicate-aware using parse ID, raw HL7 hash, request ID, or a combination.
- Reset/admin remains password-protected only for this slice; full users, roles, organizations, OAuth, and RBAC are intentionally deferred.
- `governance_events` is the canonical PHI-free audit record. Warden JSONL may remain temporarily for compatibility/debugging only, and `ai_interactions` remains protected trace data.

## Configurable Operational Defaults

- Timeouts must be configurable per stage, not hard-coded: LLM calls, SQL execution, HL7 parsing, RAG retrieval, persistence, and full request lifecycle.
- Default timeout posture: LLM longest; SQL, HL7 parse, RAG, and persistence shorter; any timeout becomes failed/interrupted with no memory commit.
- Timeout, crash, and cancellation cleanup marks incomplete records expired or interrupted. Cleanup does not resume, reinterpret, synthesize, persist, or complete clinical work.
- Trace retention must be configurable. Default should be short for demo/prototype deployments, especially for PHI-bearing `ai_interactions`.
- Production CORS/CSRF/session-cookie hardening is deferred to a later auth slice, but configuration should make local/demo vs production posture explicit.

## Practical Guardrails

- `emit_governance_event` is the only normal path for PHI-free audit writes. It accepts reason codes, counts, categories, and IDs, and rejects or redacts keys such as `raw_text`, `raw_hl7`, `question`, `history`, `answer`, `token_map`, `token_real_pairs`, `patient_name`, `dob`, and `fhir_bundle`.
- `SECURITY_CONFIG` is namespaced by `timeouts`, `ttl`, `retention`, `compatibility`, and `deployment`. It owns TTLs, timeouts, trace retention, transition mode, strictness, local/demo vs production posture, and `deployment_mode`.
- DB setup uses a simple `schema_migrations(version, applied_at)` marker plus idempotent `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`.
- Safe output helpers escape or safely render HL7, FHIR JSON display, RAG snippets, notes, and markdown-like assistant output. At least one test should prove script-like content is escaped.
- RAG metadata starts simple: `trust_level` is one of `DEMO_SEEDED_DOC`, `TRUSTED_LOCAL_DOC`, `USER_UPLOADED_UNTRUSTED`, or `UNKNOWN`, with `source_hash`, `chunk_type`, and `policy_warnings`. `DEMO_SEEDED_DOC` is bundled/demo-controlled content, `TRUSTED_LOCAL_DOC` is manually approved local content, `USER_UPLOADED_UNTRUSTED` is any uploaded or user-provided content, and `UNKNOWN` is missing-provenance or migrated content. Unknown docs are restricted or denied in high-risk flows.
- Legacy notes without new policy metadata are marked `legacy_unverified_note` at retrieval and treated as tainted clinical text.
- `llm_gateway.py` stays a dispatcher with task-specific schemas/prompts. Avoid a single giant prompt/module that mixes task behavior.
- `/messages` legacy transition mode is off by default. If enabled, old clinical fields are accepted only for compatibility, logged as ignored, recomputed server-side, and tested to never persist as authority.
- Admin/reset password comes from environment/config, missing password disables or blocks reset, and secret values are never logged.
- Invariant tests prove no ungated fallback, no direct LLM imports, no client-trusted `/messages` clinical truth, and no missing-grant tool execution.

## Storage And Indexing Defaults

- Add indexes for server-side ownership lookups and TTL cleanup:
  - `demo_sessions(session_id)`, `demo_sessions(expires_at)`
  - `conversation_states(conversation_id, session_id)`, `conversation_states(expires_at)`
  - `conversation_result_refs(result_id, session_id)`, `conversation_result_refs(expires_at)` if result refs use a separate table
  - `hl7_parse_sessions(parse_id)`, `hl7_parse_sessions(session_id, expires_at)`, `hl7_parse_sessions(status, expires_at)`
  - `governance_events(request_id)`, `governance_events(created_at)`
  - `ai_interactions(request_id)`, `ai_interactions(updated_at, status)`
- Keep parse/session/result rows small enough for fast lookup. Large raw/protected payloads should be avoided in PHI-free audit and bounded in protected trace/session tables.

## Test Plan

- Missing grant, wrong session, expired object, stale parse ID, unknown token, and extra authority fields all fail closed.
- Direct low-level LLM imports outside `llm_gateway.py` fail a static test.
- Agent failure cannot fall back to ungated legacy query.
- SQL tests cover multiple statements, comments, blocked tables, unsafe functions, missing predicates, note columns, over-limit rows, and aggregate-vs-identifier rules.
- HL7 tests cover valid ORU, non-ORU, missing MSH/PID/OBX, malformed separators, oversized fields, SQL-like notes, normal clinical instructions, and tampered client FHIR/observations.
- Memory tests prove denied, failed, interrupted, stale, timeout, and clarification-pending turns do not commit state.
- Token tests cover guessed, stale, user-injected, RAG-injected, out-of-grant, and wrong session tokens.
- Audit tests prove PHI-free event payloads and protected trace separation.
