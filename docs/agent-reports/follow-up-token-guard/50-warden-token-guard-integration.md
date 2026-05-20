# Follow-Up Report: Warden TokenGuard Integration

## Summary

Warden now uses opaque request-scoped PHI tokens and a guarded OUT-GATE restore path.

## Implementation Summary

- Replaced guessable Warden tokens such as `<<PAT_1>>` with opaque markers such as `<<PHI_PAT_...>>`.
- Added request-owned `TokenRecord` metadata inside `PHITokenMap`.
- User-facing `deanonymize` now restores only tokens that:
  - belong to the current request;
  - are registered in the current token map;
  - are still covered by a live grant;
  - have an output field type allowed by the grant.
- Guessed or out-of-grant PHI-looking tokens are redacted.
- SQL detokenization remains separate and only restores registered request tokens for database lookup.
- Agent output grant now includes the PHI field types that may be restored in governed answers.

## Validation

```text
pytest tests/test_context_builder.py tests/test_safe_memory.py tests/test_sql_guard.py tests/test_hl7_guard.py tests/test_token_guard.py tests/test_rag_calculator_guards.py tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
93 passed
```

## Residual Work

- Move Warden fully onto `TokenGuardScope` after any UI or downstream assumptions about token format are retired.
- Add PHI restore summary counts to `governance_events` for live agent responses.
- Add deterministic intent-to-grant mapping so output fields are not broad/internal defaults.
