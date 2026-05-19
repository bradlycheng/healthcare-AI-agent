# Worker Report: Warden v2 Skeleton

## Assignment

Add Phase 1 grant-aware Warden validation skeleton and exact schema enforcement.

## Changed Files

- `app/warden.py`
- `app/healthcare_agent.py`
- `tests/test_security_kernel_phase1.py`
- `tests/test_e2e_warden.py`

## Implementation Summary

- Added `IntentGrant` support to Warden request scopes.
- Warden now denies tool execution when no server-owned grant is present.
- Warden now denies tools not allowed by the active grant.
- Warden now denies expired or malformed grant expirations.
- Schema validation now rejects missing required fields and unexpected fields.
- Aligned calculator schema with the existing tool implementation using `values`.
- Updated agent query flow to create an internal Phase 1 grant before tool execution.
- Updated existing Warden tests to provide explicit grants for allowed-tool scenarios.

## Validation

- Missing-grant denial test passes.
- Expired-grant denial test passes.
- Extra-field exact-schema denial test passes.
- Existing Warden e2e suite passes with explicit grants.

## Residual Risks

- Grant source is still broad/internal for Phase 1; deterministic intent-to-grant mapping comes next.
- Tool-specific policies are still Warden v1 depth; SQLGuard/TokenGuard/CalculatorGuard deepen in Phase 2.
