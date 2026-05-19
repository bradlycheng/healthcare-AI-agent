# Lead Integration Report: Phase 2 Guard Depth

## Summary

Phase 2 guard modules were implemented in parallel and then integrated into the live query, ORU, RAG, and calculator paths.

## Integrated Guards

- SQLGuard now validates generated SQL before execution and rewrites/caps `LIMIT` using a grant.
- Hl7Guard now runs before `/oru/parse` reaches parser, persistence, or LLM enrichment.
- RAGGuard now filters vector results before prompt construction and marks accepted chunks as evidence-only.
- Calculator specs now validate calculator tool inputs before BMI/eGFR math.
- TokenGuard primitives are implemented and tested for request-scoped opaque token restore, but Warden replacement is deferred until the TokenGuard integration slice.

## Validation

```text
pytest tests/test_sql_guard.py tests/test_hl7_guard.py tests/test_token_guard.py tests/test_rag_calculator_guards.py tests/test_security_kernel_phase1.py tests/test_e2e_warden.py -q
81 passed
```

## Residual Work

- Replace Warden's legacy format-preserving token map with TokenGuard restore semantics.
- Add deterministic intent-to-grant mapping instead of Phase 1 broad/internal query grants.
- Add note-column retrieval policy to SQLGuard after product decisions on clinical note display.
- Ensure document ingestion backfills RAG metadata for all existing chunks.
- Add safe memory and dynamic context phases after guard depth stabilizes.
