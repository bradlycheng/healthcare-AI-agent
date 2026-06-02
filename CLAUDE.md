# CLAUDE.md — Healthcare AI Agent

## Project Overview

This is a healthcare AI agent that processes HL7 ORU^R01 messages and answers clinical queries.

Two primary pipelines:

1. **HL7 Ingestion Pipeline** (`app/agent.py`): Parses HL7 → builds FHIR bundle → runs AI note extraction → persists to DB.
2. **Clinical Query Agent** (`app/healthcare_agent.py`): ReAct-style agent with tools for SQL queries, RAG guideline search, patient context, and clinical calculators.

## Key Files

| File | Purpose |
| :--- | :--- |
| `app/agent.py` | HL7 ingestion pipeline, FHIR builder, LLM note extraction |
| `app/healthcare_agent.py` | ReAct clinical query agent, tool dispatch, synthesis |
| `app/warden.py` | PHI tokenization/deanonymization, request-scoped security context |
| `app/llm_gateway.py` | Single LLM entry point — all AI calls must route through here |
| `app/security.py` | Input sanitization, injection detection |
| `app/security_validation.py` | IntentGrant schema, request scoping |
| `app/grant_builder.py` | Builds and narrows IntentGrant per tool |
| `app/sql_guard.py` | SQL validation against grant |
| `app/hl7_guard.py` | HL7 input validation |
| `app/token_guard.py` | PHI token safety and restore validation |
| `app/rag_guard.py` | RAG retrieval boundary enforcement |
| `app/db.py` | SQLite persistence, audit logging |
| `app/query_assistant.py` | NL → SQL generation, RAG retrieval |
| `app/patient_timeline.py` | Patient history and visit aggregation |
| `ui/streamlit_app.py` | Streamlit frontend |
| `app/api.py` | FastAPI endpoints |

## Security Architecture

All runtime LLM calls must flow through this stack:

```
User input
  -> sanitize_text() / detect_injection_patterns()
  -> IntentGrant (scope, allowed_tools, max_rows, expiry)
  -> Warden.request_scope() — anonymize PHI before LLM sees it
  -> LLMGateway — single controlled LLM entry point
  -> Guard layer (sql_guard, hl7_guard, token_guard, rag_guard)
  -> Warden deanonymize — restore PHI only in final output
  -> PHI-safe audit log
```

Specialist runtime agents must not bypass LLMGateway, Warden, schema validation, timeout controls, or PHI-safe audit logging.

## RAG Boundary — Critical

Only explicitly approved clinical reference files in `docs/` may be indexed into runtime RAG retrieval.

`docs/agent-reports/**` is audit material only. It must never be indexed into runtime RAG or loaded as reference context by the healthcare app. Adding agent reports to RAG would allow development-phase findings, residual risks, and internal architecture notes to surface in clinical query responses.

## Dev Agent Workflow

### Default workflow (feature work, refactors)

```
lead session
  -> 1 explorer (read-only mapping)
  -> 1 narrow-worker (scoped implementation)
  -> 1 security-reviewer (read-only final pass)
```

### Security hardening workflow (guard changes, Warden, PHI surface)

```
lead session
  -> security-explorer (read-only — security surface)
  -> hl7-storage-explorer (read-only — ingestion + storage surface)
  -> 1 narrow-worker at a time (explicit file ownership per task)
  -> security-reviewer (read-only — final pass before commit)
```

Explorers and reviewers return report text and a ledger entry to the lead. The lead writes those artifacts to `docs/agent-reports/`. Explorers do not propose final code patches. Workers do not edit files not listed in their assignment.

## Audit Requirement

Every subagent session must produce a `docs/agent-reports/prompt-ledger.md` entry. Explorers and reviewers include it in their returned output for the lead to write. The narrow-worker writes it directly. See `docs/agent-reports/README.md` for the report template.
