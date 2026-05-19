# Phase 2 Worker Report: RAG And Calculator Guards

## Scope

Owned files:

- `app/calculator_specs.py`
- `app/rag_guard.py`
- `tests/test_rag_calculator_guards.py`
- `docs/agent-reports/phase-2-guard-depth/23-worker-rag-calculator-guards.md`

No integration changes were made to `app/healthcare_agent.py`.

## Calculator Guard

Implemented hard-coded specs for:

- `bmi`: accepts only `weight_kg` and `height_m`.
- `egfr`: accepts only `creatinine`, `age`, and `sex`.

The validator rejects:

- unsupported calculators
- extra top-level fields such as `params`
- extra calculator values
- identifiers and PHI-bearing fields such as `patient_id`, `patient_name`, `dob`, and `mrn`
- raw rows, raw HL7, FHIR, notes, SQL, code, and custom formula fields
- wrong primitive types
- out-of-range numeric values

The validator returns normalized values, accepted fields, and the expected output shape for later lead integration.

## RAG Guard

Implemented RAG chunk helpers that treat retrieved content as evidence only. Accepted chunks are normalized into `TrustedRagChunk` with:

- `evidence_only=True`
- safe metadata only: `trust_level`, `source_hash`, `chunk_type`, optional bounded `policy_warnings`
- original text preserved as untrusted evidence, not instruction authority

The filter requires server-side metadata:

- `trust_level`
- `source_hash`
- `chunk_type`

The filter rejects chunks with:

- missing or invalid trust metadata
- insufficient trust level
- role spoofing in text
- metadata that claims authority, roles, grants, permissions, output authorization, or instructions
- hidden/control unicode
- long base64, hex, or percent-encoded blobs
- oversized chunk text

Also included a Chroma result coercion helper so lead integration can convert existing vector-store query results without changing retrieval internals in this slice.

## Tests

Focused test coverage lives in `tests/test_rag_calculator_guards.py` and covers:

- hard-coded calculator spec inventory and output shape
- valid BMI request normalization
- rejection of extra params, identifiers, raw rows, notes, and formulas
- type and range failures
- accepted trusted RAG chunks as evidence-only
- rejection of role spoofing, hidden unicode, encoded blobs, untrusted metadata, and authority-claiming metadata
- Chroma result coercion into guard input

Run command:

```powershell
pytest tests/test_rag_calculator_guards.py
```
