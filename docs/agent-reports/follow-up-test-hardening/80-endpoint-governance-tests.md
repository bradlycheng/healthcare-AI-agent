# Follow-Up Report: Endpoint Governance Test Hardening

## Summary

Added endpoint-level governance tests to lock in current kernel behavior before building additional stateful features.

## Coverage Added

- `/oru/parse persist=false` returns a server-owned `parse_id`.
- `/messages` persists by same-session `parse_id`.
- Parse ID replay fails.
- Wrong-session parse ID fails.
- Client-tampered patient, observation, summary, raw HL7, and FHIR fields do not become authoritative.
- `governance_events` records safe reason codes for parse creation, persistence, invalid parse ID, missing parse ID, HL7 guard denial, classifier denial, and classifier failure.
- Governance event payloads are checked for PHI/raw-data leakage.
- Classifier failure and deny labels do not call the agent.
- Expired parse sessions and conversation state are unusable through current helpers.

## Validation

```text
C:\Users\bradl\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m compileall -q app tests
pytest tests/test_endpoint_governance.py tests/test_static_compile_imports.py tests/test_intent_classifier.py tests/test_grant_builder.py tests/test_context_builder.py tests/test_safe_memory.py tests/test_sql_guard.py tests/test_hl7_guard.py tests/test_token_guard.py tests/test_rag_calculator_guards.py tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
112 passed
```

## Residual Work

- Build the full interruption reconciler/cleanup job.
- Add reference and scope-jump resolver tests alongside that implementation.
- Update frontend parse-id save flow in a separate UI compatibility slice.
