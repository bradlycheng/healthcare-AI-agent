# Worker Report: HL7 And Messages Governance

## Assignment

Wire `/oru/parse` and `/messages` into server-owned parse-session governance.

## Changed Files

- `app/api.py`
- `app/db.py`
- `app/security_validation.py`
- `tests/test_security_kernel_phase1.py`

## Implementation Summary

- `/oru/parse persist=false` now creates a server-owned parse session with `parse_id`, `session_id`, raw HL7 hash, status, expiry, and server parse result.
- `ORUParseResponse` now includes optional `parse_id`.
- `/messages` requires a valid same-session, unexpired `parse_id` by default.
- `/oru/parse` rejects direct persistence by default; compatibility is behind `SECURITY_ALLOW_ORU_DIRECT_PERSIST`.
- `/messages` atomically claims a parse session before save so each `parse_id` can be persisted once.
- `/messages` persists server-owned parse result data instead of client-supplied clinical JSON.
- Legacy `/messages` compatibility remains off by default behind `SECURITY_ALLOW_LEGACY_MESSAGES`.
- Safe public error response now avoids raw exception text for message-save errors.
- HL7 parse execution is wrapped in a configurable timeout.

## Validation

- `/messages` rejects client-created clinical JSON without `parse_id`.
- `/oru/parse persist=true` rejects by default.
- Parse-session claim is one-time.
- Phase 1 tests and Warden e2e suite pass.

## Residual Risks

- Frontend confirm-save still needs a follow-up update to submit `parse_id`.
- Full HL7 note policy, SQL-like note denial, and note persistence belong to Phase 2 Hl7Guard.
