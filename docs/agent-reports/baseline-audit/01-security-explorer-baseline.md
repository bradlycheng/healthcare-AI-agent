# Agent Report: security-explorer

## Assignment
Baseline security audit -- Warden, grants, LLMGateway, query flow, PHI leakage, RAG, SQLGuard, TokenGuard, audit logging.

---

## Files Inspected

**Core Security:**
- app/warden.py (903 lines) -- Presidio-pattern tokenization engine
- app/security_validation.py (232 lines) -- Grant/session/audit structures
- app/security.py (114 lines) -- Injection pattern detection
- app/token_guard.py (229 lines) -- PHI token safety and restore validation

**Guards:**
- app/sql_guard.py (468 lines) -- SELECT-only validator with table/column/function restrictions
- app/hl7_guard.py (226 lines) -- Message format and size validator
- app/rag_guard.py (247 lines) -- Trust level + role spoofing validator

**Query Flow:**
- app/query_assistant.py (700+ lines) -- SQL generation + RAG retrieval
- app/healthcare_agent.py (1200+ lines) -- ReAct-style agent with tool orchestration
- app/llm_gateway.py (50 lines) -- Wrapper around llm_client
- app/llm_client.py (289 lines) -- Direct Bedrock invoke_model calls

**Data/Config:**
- app/grant_builder.py (135 lines) -- Intent classification -> grant construction
- app/document_loader.py (195 lines) -- RAG document chunking
- app/rag_config.py (20 lines) -- RAG chunk/embedding settings
- app/api.py (850+ lines) -- FastAPI endpoints
- app/embeddings.py (76 lines) -- Bedrock Titan embedding calls
- app/vector_store.py (116 lines) -- ChromaDB with cosine distance

---

## Current Flow

### 1. PHI Handling (Warden Tokenization)

**IN-GATE (Anonymize before LLM):**
- `healthcare_agent.py:352-358`: Questions and history are tokenized before agent planning
- `warden.py:355-362`: `WardenAnonymizer.anonymize()` applies format-preserving tokens
- Tokens: `<<PHI_PAT_HEXVALUE>>`, `<<PHI_PID_HEXVALUE>>`, `<<PHI_DOB_HEXVALUE>>`, `<<PHI_PROV_HEXVALUE>>`
- `WardenAnalyzer.build_token_map()` (line 266-341): Scans `hl7_messages`, `visits` tables for patient names, IDs, DOBs, provider names
- Tokens are session-pinned, ephemeral (RAM-only), cleared on context exit

**DOUBLE-BLIND SQL:**
- `healthcare_agent.py:438-446`: Tool input is deanonymized before database execution
- `warden.py:384-392`: `deanonymize_sql()` restores real values in SQL WHERE clauses
- SQL executes against real data; results are then re-tokenized

**OUT-GATE (Detokenize for user):**
- `healthcare_agent.py:513-514`: LLM response and highlights are detokenized
- `warden.py:154-171`: `detokenize()` validates token records against grant scope + request/session ID
- Only tokens with `output_authorized=True` and matching request scope are restored
- Guessed/stale tokens are redacted as `[REDACTED_PHI_TOKEN]`

**Clinical Surrogation:**
- `warden.py:700-740`: `ClinicalSurrogator` level="PASS" -- medications/diagnoses pass through untokenized in demo mode
- Production hooks documented for RxNorm class mapping and ICD-10 rollup

### 2. LLM Gateway

- `llm_gateway.py`: Thin wrapper around `llm_client.py`
- All AI calls route through: `call_llm_text()`, `call_llm_json()`, `agent_planning()`, `sql_generation()`, `agent_synthesis()`, `deep_reflection()`
- `llm_client.py:222` and `llm_client.py:274` directly invoke Bedrock via `bedrock_runtime.invoke_model()`
- No gatekeeping in `llm_client.py` itself; security is upstream in prompt handling

### 3. Grant and Policy Enforcement

- `build_query_grant()`: Denies admin/delete/export/policy_override intents; assigns tools by intent; caps max_rows at 200; expires in 5 minutes
- `WardenPolicy.intercept()`: Checks grant is live -> validates tool is in allowed_tools -> strict type-checks against TOOL_SCHEMAS -> blocks jailbreak tokens -> runs tool-specific rules
- Tool-specific: SQLGuard validates query content; patient context cross-checks grant.subject; calculator whitelist-only (bmi, egfr)

### 4. Guard Layer

**SQLGuard:** Blocks DDL, no semicolons, SELECT-only, no UNION/WITH/EXCEPT, table/column allowlists, function whitelist, injects LIMIT up to grant.max_rows. Very tight. Does not validate patient-scope narrowing.

**HL7Guard:** Validates MSH structure, caps message size (64KB), detects SQL-like patterns in NTE-3 and OBX-5.

**TokenGuard:** Only restores tokens from request-local registry; validates session/request ID match, grant liveness, output_authorized=True, trusted source. Redacts stale/guessed tokens.

**RAGGuard:** Validates chunk metadata (trust_level, source_hash, chunk_type); rejects role spoofing; rejects hidden Unicode and encoded blobs. Does not scan chunk content for PHI.

### 5. Audit Logging

- `warden.py:762-781`: Audit entry records phi_fields_anonymized count and field_types categories only -- never actual tokens or real values
- `AUDIT_BLOCKED_KEYS` in security_validation.py blocks history, raw_hl7, token_map, fhir_bundle, answer from audit payloads

---

## Risks / Bypasses

### CRITICAL

**C1 -- RAG Embeddings Expose Queries to Bedrock Without Tokenization**
- `query_assistant.py:378-447` -> `vector_store.py:79-99` -> `embeddings.py:28-58`
- `retrieve_context(question)` calls `embed_text(question)` which sends the raw question to Bedrock Titan
- If the question contains real patient names (pre-tokenization code path or legacy path), PHI leaks to Bedrock
- No Warden gate in `vector_store.py` or `embeddings.py`
- **Action**: Wrap embed calls in Warden context; tokenize before embedding

**C2 -- Token Map Is Incomplete for Unregistered Names**
- `build_token_map()` queries existing DB records only
- New patient names supplied in a query but not yet in DB will not be tokenized
- Real names in user input pass through to LLM if not in token map
- **Action**: Add heuristic name pattern tokenizer for unregistered name-like strings

**C3 -- ORU Pipeline LLM Call Bypasses Warden**
- `agent.py`: `hl7_note_extraction()` is called outside a Warden request scope
- PHI in HL7 clinical notes is sent to LLM without tokenization
- **Action**: Wrap `hl7_note_extraction()` in a Warden scope; tokenize notes before extraction

### WARNING

**W1 -- RAG Documents Not Scanned for PHI Before Indexing**
- `document_loader.py:137-164`: Documents chunked and indexed without PHI check
- If a clinical note or agent report is accidentally placed in the docs directory, it will be indexed
- `rag_guard.py` validates metadata only; no PII regex on chunk content
- **Action**: Add PHI scanner to document_loader; validate content against trust_level

**W2 -- Embedding Text Sent to Bedrock in Cleartext During Indexing**
- `vector_store.py:69` (add_documents) calls `embed_text(text[:8000])` with full document text
- No Warden gate; documents with clinical content would be sent to Bedrock for embedding
- **Action**: Tokenize document text before embedding, or require trust_level to prohibit real PHI in RAG docs

**W3 -- Grant Subject Narrowing Is Advisory, Not Enforced at SQLGuard**
- If grant has subject=patient_123, the query prompt appends "for patient patient_123" (advisory)
- SQLGuard validates tables/columns but not patient scope
- LLM-generated SQL could access different patients if prompt injection succeeds
- **Action**: Document limitation or add subject validation to SQLGuard

**W4 -- FHIR Bundle Returned in ORU Parse Response Without Access Control**
- POST /oru/parse returns full FHIR Bundle including all clinical observations
- No role-based filtering; any authorized caller gets complete clinical data
- Cross-reference with hl7-storage-explorer findings

### INFORMATIONAL

**I1 -- Error Messages May Echo Guard Reasons (Schema Disclosure)**
- `healthcare_agent.py:785`: "Invalid SQL: {guard_result.reason}" echoes guard decision
- Low risk (schema is semi-public) but guard reasons should be internal-only
- **Action**: Scrub guard reasons from user-facing errors; log full reasons to audit

**I2 -- SQL Generation Prompt Uses Patient-Like Example Names**
- `query_assistant.py:123-207`: SQL examples use "John Smith", "Sarah Jenkins", etc.
- Not actual PHI, but primes LLM to generate non-tokenized names in SQL
- **Action**: Replace with generic placeholders (PatientA, TestName_001)

**I3 -- Rate Limiting Is Per-IP, Not Per-Session**
- Shared IP can cause one user to block others
- **Action**: Include session_id in rate limit key

**I4 -- Warden Audit Log Is Good (Confirmation)**
- Audit records phi_fields_anonymized count and field_types only -- never real values
- AUDIT_BLOCKED_KEYS prevent raw data from appearing in logs
- This is working correctly; no action needed

---

## Recommended Implementation Notes

### High Priority

1. **Wrap `embed_text()` calls in Warden context** -- add optional token_map parameter; tokenize before embedding in both `vector_store.py:69` (indexing) and `vector_store.py:93` (search)
2. **Wrap HL7 note extraction in Warden scope** -- `agent.py` hl7_note_extraction call needs anonymize/deanonymize around the LLM call
3. **Add PHI scanner to document_loader** -- PHI regex (MRN, phone, SSN, patient name patterns) before chunking; reject or require elevated trust_level

### Medium Priority

4. **Heuristic name tokenizer for unregistered names** -- pattern-match "FirstName LastName" strings even if not in DB; log as provisional tokens
5. **Tokenize user queries before RAG retrieval** -- pass tokenized question to `retrieve_context()` instead of raw question
6. **Scrub guard reasons from API error responses** -- user gets generic message; full reason goes to audit log only
7. **Replace SQL example names with generic placeholders**

### Low Priority

8. **Add patient subject validation to SQLGuard** -- if grant.subject present, validate SQL WHERE clause targets that patient
9. **Session-based rate limiting** -- add session_id to rate limit key alongside IP

---

## Tests To Add

1. PHI tokenization coverage -- verify all known patient names are tokenized before LLM call
2. Token isolation -- cross-request token reuse must fail (tokens from request A cannot restore in request B)
3. RAG guard content validation -- document with embedded patient names is flagged or rejected
4. Embedding anonymization -- verify embed_text() is called only on tokenized strings
5. Grant subject narrowing -- query with subject=patient_123 only accesses that patient
6. HL7 guard SQLi detection -- SQL patterns in NTE-3 / OBX-5 are rejected
7. Error message sanitization -- API error responses don't echo schema or guard reasons
8. Audit log integrity -- audit log never contains raw_hl7, patient_name, fhir_bundle, or answer
9. Injection pattern detection -- all BLOCKED_COMMAND_TOKENS and INJECTION_PATTERNS are caught
10. ORU note extraction PHI -- PHI in HL7 notes is tokenized before LLM extraction call

---

## Open Questions

1. Is RAG enabled in production? If yes, docs must be pre-scanned. If no, disable embedding calls.
2. What is the auth model for `/api/docs/upload`? No auth visible in api.py -- admin-only or disabled in production?
3. Are HL7 messages anonymized before being returned in any API response? Currently: no (ORU parse returns real names).
4. Is deep reflection mode enabled in production? If yes, ensure all reflection prompts are anonymized.
5. What are the audit log retention and access policies? Currently filesystem (`warden_audit.jsonl`).
6. Should grant subjects support multi-patient sets (care team use case)?
7. Are clinical surrogation hooks (RxNorm, ICD-10 rollup) planned before production?
