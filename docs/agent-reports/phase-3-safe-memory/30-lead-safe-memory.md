# Lead Integration Report: Phase 3 Safe Memory

## Summary

Phase 3 adds a minimal safe-memory commit gate for demo sessions. It stores typed metadata only after a successful governed query turn.

## Implementation Summary

- Added `app/safe_memory.py`.
- Added DB helpers for loading and upserting active `conversation_states`.
- `/api/query` now loads safe state metadata at request start and emits whether state exists.
- `/api/query` commits memory only after successful, non-clarification, non-error turns.
- Agent responses now include internal `safe_metadata` extracted from tool results.

## Stored Fields

- `patient_ids`
- `topic_codes`
- `result_ids`
- `scope`
- `intent`
- `expires_at`

## Explicitly Not Stored

- raw user question
- raw assistant answer
- raw history
- free-text last topic
- permissions or admin claims
- prior assistant claims as authority

## Validation

```text
pytest tests/test_safe_memory.py tests/test_sql_guard.py tests/test_hl7_guard.py tests/test_token_guard.py tests/test_rag_calculator_guards.py tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
87 passed
```

## Residual Work

- Add deterministic reference resolution for pronouns and ordinal references.
- Add explicit scope-jump clarification/deny policy before using prior state.
- Move TTL duration to the central config for this module instead of the current 30-minute default.
- Add cleanup job for expired states and result refs.
