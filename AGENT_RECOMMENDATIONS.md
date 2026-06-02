# Healthcare AI Agent — CLAUDE.md

## Project Overview
A healthcare interoperability agent that parses HL7 v2 ORU messages, converts them to FHIR R4, and uses AWS Bedrock (Llama 3.8B) for clinical AI summaries. Governance-first design with HIPAA/NIST compliance.

## Stack
- **Backend**: Python 3.9+, FastAPI, Uvicorn
- **Database**: SQLite (WAL mode) via `app/db.py`
- **LLM**: AWS Bedrock — `meta.llama3-8b-instruct-v1:0`
- **HL7 Parsing**: `hl7apy`
- **FHIR**: `fhir.resources`
- **Vector Store**: ChromaDB (RAG over clinical guidelines)
- **Frontend**: Static HTML/CSS/JS in `web/`
- **Reverse Proxy**: Caddy 2
- **Tests**: pytest

## Running Locally
```bash
pip install -r requirements.txt
aws configure          # region: us-east-1
uvicorn app.api:app --reload
# http://localhost:8000
```

## Running with Docker
```bash
docker compose up -d
# http://localhost:8080
```
AWS credentials are mounted from `~/.aws` — Bedrock access required.

## Running Tests
```bash
pytest tests/                                          # all tests
pytest tests/test_security_kernel_phase1.py -v        # security kernel
pytest tests/test_endpoint_governance.py -v           # endpoint governance
pytest tests/test_sql_guard.py -v                     # SQL whitelist
```
Test database is `agent_test.db` (separate from `agent.db`).

## Key Entry Points

| File | Purpose |
|------|---------|
| `app/api.py` | FastAPI routes — start here |
| `app/agent.py` | HL7 → FHIR → LLM pipeline |
| `app/healthcare_agent.py` | ReAct query agent (NL → SQL + RAG) |
| `app/llm_gateway.py` | Governance-controlled LLM access layer |
| `app/llm_client.py` | Raw AWS Bedrock client |
| `app/hl7_parser.py` | HL7 v2.5.1 parsing (MSH/PID/OBR/OBX/NTE) |
| `app/fhir_builder.py` | FHIR R4 Bundle generation |
| `app/warden.py` | MCP Warden — policy enforcement (IN/POLICY/OUT gates) |
| `app/intent_classifier.py` | Query intent classification + DENY list |
| `app/grant_builder.py` | Capability grants (5-min TTL, tool narrowing) |
| `app/sql_guard.py` | SQL whitelist enforcement |
| `app/token_guard.py` | PHI tokenization/detokenization |
| `app/safe_memory.py` | Conversation state (30-min TTL, injection-resistant) |
| `app/security_validation.py` | Config TTLs, timeouts, audit redaction |
| `app/db.py` | SQLite connection pool + schema |

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/oru/parse` | Parse HL7 ORU message, return FHIR bundle |
| `POST` | `/api/query` | Natural language query (ReAct agent) |
| `GET` | `/messages` | List all ingested HL7 messages |
| `GET` | `/patients` | Patient list with visit counts |
| `GET` | `/patients/{id}/timeline` | Patient visit history |
| `POST` | `/messages` | Persist parsed HL7 to DB |
| `DELETE` | `/messages` | Reset DB (requires `ADMIN_PASSWORD`) |
| `GET` | `/ping` | Liveness check |

## Security Architecture (Do Not Bypass)
The project has a layered governance kernel — every LLM call flows through `llm_gateway.py`, never directly through `llm_client.py`.

**Pipeline per query:**
1. `hl7_guard.py` — reject malformed/non-ORU messages
2. `security.py` — sanitize input, detect prompt injection
3. `intent_classifier.py` — classify + DENY admin/delete/export intents
4. `warden.py` IN-GATE — tokenize PHI before LLM
5. `grant_builder.py` — build capability grant (allowed tools, row limits)
6. `healthcare_agent.py` — ReAct loop with tool calls
7. `sql_guard.py` — whitelist SQL before execution
8. `warden.py` OUT-GATE — detokenize + redact output

**SQL whitelist** (allowed tables): `hl7_messages`, `observations`, `visits`, `medications`, `diagnoses`
**Blocked intents**: `admin`, `delete`, `export`, `reset`, `policy_override`, `system_prompt_request`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | Bedrock region |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | LLM model |
| `DATABASE_PATH` | `agent.db` | SQLite path |
| `ADMIN_PASSWORD` | `d3m0th1s` | DB reset password |
| `SECURITY_ALLOW_LEGACY_MESSAGES` | `false` | Allow pre-governance HL7 |
| `SECURITY_ALLOW_ORU_DIRECT_PERSIST` | `false` | Skip parse session TTL |
| `SECURITY_SHOW_PROTECTED_OUTPUT` | `false` | Show tokenized debug output |

## Important Gotchas
- **Rate limiting**: 5-second cooldown between LLM calls enforced in `api.py`
- **Parse sessions**: HL7 parse results have a 10-min TTL before persistence — don't skip this step
- **Thread safety**: DB connections are thread-local; agent runs in `ThreadPoolExecutor` to avoid blocking FastAPI's event loop
- **PHI tokenization**: Token maps are request-scoped; `safe_metadata` carries them through for detokenization
- **Grant expiry**: Capability grants expire after 5 minutes — don't cache them
- **Max rows**: Query results capped at 50 (hard limit 200) via grant builder

## Database Reset
```bash
# Via API
curl -X DELETE http://localhost:8080/messages \
  -H "Content-Type: application/json" \
  -d '{"password":"d3m0th1s"}'
```

## Compliance
- HIPAA Safe Harbor (6/18 identifiers tokenized)
- NIST AI RMF (data minimization, intent validation)
- Colorado AI Act (reasonable care governance)
- OWASP Agentic Top 10 (tool validation, prompt injection defense)
