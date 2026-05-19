# Reviewer Security Pass: Phase 1 Kernel Spine

## Summary

Reviewer pass found blocking Phase 1 gaps after the initial kernel spine. Lead Codex fixed the blocking items before commit.

## Findings And Resolution

- Critical: PHI read endpoints bypassed the new audit/session layer.
  - Resolution: Added governance audit events and demo-session ownership to patient and message read endpoints.

- Critical: `/oru/parse` still allowed direct persistence when `persist=true`.
  - Resolution: Direct ORU persistence is disabled by default; `/oru/parse` now previews and issues a `parse_id`, then `/messages` persists the server-owned parse result.

- High: Warden grant presence was checked, but grant freshness was not.
  - Resolution: Warden now denies expired or malformed grant expirations.

- High: Patient journey summaries still included direct patient identity in the LLM prompt.
  - Resolution: Summary prompt now withholds direct identifiers and uses only minimal clinical context.

- Medium: Parse sessions could be replayed between validation and persistence.
  - Resolution: `/messages` now atomically claims a parse session before save; a parse ID can be used once.

- Medium: Timeout behavior was configured but not enforced on HL7 parse.
  - Resolution: `/oru/parse` now uses the configured HL7 parse timeout and logs timeout denial.

## Validation

```text
pytest tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
35 passed
```

## Residual Risk

- Full SQLGuard, Hl7Guard note policy, TokenGuard restore, RAG trust filtering, safe memory, and dynamic context remain in later phases.
- Phase 1 still uses a broad internal query grant until deterministic intent-to-grant mapping lands.
- Read endpoints now have audit/session coverage, but full RBAC/output gating remains deferred.
