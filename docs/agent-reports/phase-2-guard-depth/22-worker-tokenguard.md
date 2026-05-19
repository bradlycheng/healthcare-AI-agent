# Worker Report: TokenGuard

## Assignment

Implement request-scoped opaque token restore primitives without replacing Warden tokenization yet.

## Changed Files

- `app/token_guard.py`
- `tests/test_token_guard.py`
- `docs/agent-reports/phase-2-guard-depth/22-worker-tokenguard.md`

## Files Inspected

- `app/security_validation.py`
- `app/warden.py`
- `tests/test_security_kernel_phase1.py`
- `tests/test_e2e_warden.py`
- `docs/agent-reports/README.md`
- `docs/agent-reports/phase-1-kernel-spine/12-worker-warden-v2.md`

## Implementation Summary

- Added `TokenGuard` and `TokenGuardScope` as an integration-ready API for future lead wiring.
- Tokens are opaque, request-local values shaped like `<<PHI_PAT_...>>`.
- Public metadata uses the existing `TokenRecord` contract from `app/security_validation.py`.
- Real values stay in the request-local scope only and are excluded from audit summaries.
- Restore fails closed unless the token belongs to the current request, current session, live grant, trusted source, output-authorized record, and a field type listed in `grant.output_fields`.
- Guessed, stale, wrong-request, wrong-session, expired-grant, user-injected, RAG-injected, output-disabled, and out-of-grant tokens are redacted.
- Added a metadata-only helper that intentionally cannot restore values without the request-local real-value registry.

## Validation

- `pytest tests\test_token_guard.py -q`
- Result: `10 passed in 1.15s`

## Residual Risks

- TokenGuard is not yet wired into Warden, RAG, or the LLM gateway; this worker exposes primitives only.
- `TokenRecord` does not include a session id, so session binding is enforced by `TokenGuardScope` and the active `IntentGrant`.
- Field authorization currently requires exact `grant.output_fields` membership or `*`; lead integration should decide the final grant vocabulary.
