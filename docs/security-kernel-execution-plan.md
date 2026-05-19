# Security Kernel and Warden v2 Execution Plan

## Summary

This is the implementation rollout plan for the Warden v2 / Security Kernel target architecture. It is intentionally separate from the target design so reviewers can distinguish the finished architecture from the order of work.

## Rollout Strategy

- Use a broad but shallow first slice to route the major sensitive paths through the kernel early: `/api/query`, `/oru/parse`, and `/messages`.
- Keep Phase 1 focused on contracts, ownership, grants, exact schemas, parse-session status, server-owned persistence, no ungated fallback, PHI-safe audit, and fail-closed behavior.
- Deepen guard behavior in later phases after all high-risk paths are behind the kernel.

## Sandbox And Approval Setup

- Current sandbox state is up to date: `workspace-write` is active, network is restricted, and writable roots are the project workspace plus `C:\tmp`.
- The sandbox is enough to begin. No extra sandbox button/setup is needed before Phase 0 mapping.
- Add a project policy on top of the sandbox before using multiple agents: Phase 0 agents are read-only explorers; worker agents do not edit until the mapping report is reviewed.
- Allowed without extra approval: read files, search code, inspect tests, map endpoints, and run non-mutating checks.
- Needs explicit user go-ahead by project policy: implementation edits, migrations, dependency installs, network access, GUI/browser launch, destructive commands, reset/delete operations, and any change outside the workspace.
- For multi-agent work, every agent gets a narrow scope and a named output. The lead integrates; sub-agents do not decide architecture or merge their own work.
- Agent reports and handoff notes live under `docs/agent-reports/`, organized by phase. Agents themselves do not live in Markdown files; the files are their outputs.
- This policy is necessary for multi-agent security work because the sandbox controls permissions, while the project policy controls coordination and architectural authority.

## Rollout Alternatives

- Broad kernel spine first: route `/api/query`, `/oru/parse`, and `/messages` through thin kernel enforcement before deepening each guard. Pros: closes bypasses early, proves shared metadata/audit/session contracts, and prevents building new features around old unsafe paths. Cons: Phase 1 has more surface area, some guards start as strict stubs, and demo behavior may feel temporarily narrower.
- Endpoint-by-endpoint depth first: fully harden one endpoint, then move to the next. Pros: easier local reasoning, deeper tests per endpoint, and fewer simultaneous moving parts. Cons: old endpoints remain bypass paths longer, shared interfaces may churn, and duplicated local patterns can form before the kernel stabilizes.
- Warden-only refactor first: rebuild tool validation before touching HL7, `/messages`, memory, RAG, or output. Pros: smallest code change and useful if agent tools are the only immediate concern. Cons: it does not protect parse/persist/token/RAG boundaries and can create false confidence because high-risk non-tool paths remain outside the kernel.

Recommendation: use the broad kernel spine first. This matches the target architecture because the main risk is bypass, not just weak validation inside one component.

## Phases

- Phase 1: build the security spine with minimal context: typed contracts, central config, PHI-safe audit helper, kernel orchestration, session ownership, Warden v2 grant checks, gateway-only LLM calls, no ungated fallback, parse-session status, `/messages` server-owned persistence, initial guard stubs, safe output escaping helper, and phase-gate invariant tests.
- Phase 2: fill in guard depth: SQL disclosure policy, note ingress/retrieval policy, request-scoped token restore, RAG trust metadata, calculator specs, and admin grant enforcement.
- Phase 3: add safe memory: `conversation_states`, result refs, TTL, state commit gate, ownership binding, and scope-jump tests.
- Phase 4: add bounded dynamic context through `ContextBuilder`: pre-grant context uses only safe state, planning context uses grant/safe summaries, synthesis context uses grant-scoped tool results/RAG/notes.
- Phase 5: add richer context and operational hardening: patient timeline context, note-review context, RAG poison handling, production CORS/CSRF/auth slice, trace retention jobs, and legacy data scanning/backfill if needed.

## Test And Validation Gates

- Static boundary tests: validate no direct low-level LLM imports outside `llm_gateway.py`, no ungated legacy `/api/query` fallback, no tool execution without Warden v2, and no client clinical JSON used as authority in `/messages`.
- Contract tests: validate exact schemas, rejection of extra fields, grant expiry, session ownership, parse-session status, and configurable timeout behavior.
- Endpoint tests: exercise `/api/query`, `/oru/parse`, `/messages`, read endpoints, and reset/admin paths through the kernel entrypoints.
- Guard tests: validate SQL AST/policy, HL7 structure/note policy, TokenGuard restore/redact, RAG trust filtering, calculator specs, output escaping, and note retrieval taint.
- Abuse tests: prompt injection, metadata injection, encoded payloads, fake tool JSON/XML/YAML, stale IDs, wrong-session IDs, guessed tokens, client-tampered FHIR/observations, and interrupted/timeout flows.
- Audit tests: validate `governance_events` payloads are PHI-free, include request/session/component/reason metadata, and never contain raw HL7, raw question/history/answer, token maps, FHIR bundles, patient names, DOB, or stack traces.
- Regression tests: keep existing happy-path demo behavior for valid clinical query, valid ORU parse preview, parse persistence by `parse_id`, and normal doctor-note instructions.

## Phase 1 Acceptance Criteria

- No direct low-level LLM imports outside `llm_gateway.py`.
- `/api/query` cannot fall back to ungated legacy query handling.
- `/messages` cannot persist client-generated patient, observation, summary, FHIR, status, trust, or authorization fields as authority.
- Tool execution requires a server-owned grant and exact schema.
- Parse sessions require status, session ownership, TTL, and server-owned parse result.
- `governance_events` writes go through the PHI-safe helper.
- Missing grant, wrong session, stale parse ID, unknown token, extra authority field, timeout, and interrupted request fail closed.
- Phase 1 stubs deny unknown/unsupported cases by default.
