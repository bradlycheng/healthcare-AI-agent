# Worker Report: Hl7Guard

## Assignment

Implement a deterministic HL7 input and note validation helper for Phase 2 guard depth without wiring it into the API yet.

## Owned Files

- `app/hl7_guard.py`
- `tests/test_hl7_guard.py`
- `docs/agent-reports/phase-2-guard-depth/21-worker-hl7guard.md`

## Implementation Summary

- Added `validate_hl7_message` as the lead-integration API for raw HL7 ingress checks.
- Added explicit result dataclasses: `Hl7GuardConfig`, `Hl7GuardIssue`, and `Hl7GuardResult`.
- Enforced deterministic caps for message size, segment count, segment length, field count, field length, and note length.
- Rejected null bytes before parser, storage, or LLM enrichment.
- Required the first non-empty segment to be `MSH`.
- Required `MSH-9` to identify an `ORU` message.
- Required at least one `PID` segment and at least one result-like `OBR` or `OBX` segment.
- Applied SQL-like note denial only to `NTE-3` and text-like `OBX-5` values.
- Preserved normal clinical instructions such as medication continuation and orders for follow-up labs.
- Returned only reason codes and counts in metadata, not raw HL7 or note text.

## Tests

- Valid ORU with normal clinical NTE note.
- Null byte rejection.
- Leading non-MSH segment rejection.
- Non-ORU message rejection.
- Missing PID rejection.
- Missing OBR/OBX result segment rejection.
- Message, segment, field, and note cap enforcement.
- SQL-like NTE-3 denial.
- SQL-like text OBX-5 denial.
- Numeric OBX-5 does not receive note SQL policy.

## Integration Notes

- API integration should call `validate_hl7_message(hl7_text)` before `parse_oru`, parse-session creation, persistence, or LLM note extraction.
- Public responses should map `Hl7GuardIssue.code` to safe client errors and keep raw notes/HL7 out of logs and audit payloads.
- Runtime deployments can tune caps through `Hl7GuardConfig` if Phase 2 lead chooses environment-driven values.

## Residual Risks

- The SQL-like note detector is intentionally conservative and deterministic; it denies obvious SQL/control text rather than attempting broad prompt-injection classification.
- `/oru/parse` and `/messages` are not yet wired to this guard by assignment.
