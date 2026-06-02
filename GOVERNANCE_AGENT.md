# Governance / Audit Agent

## Role
Monitor the `governance_events` table for anomalies, generate compliance reports, and surface policy violations. Read-only — this agent never writes clinical data or calls the LLM on patient records.

## Entry Points
| File | Purpose |
|------|---------|
| `app/warden.py` | MCP Warden — source of all governance events |
| `app/security_validation.py` | Config TTLs, timeouts, `audit_safe_payload()` redaction |
| `app/intent_classifier.py` | Intent deny list and scope definitions |
| `app/grant_builder.py` | Grant schema — what was allowed vs. requested |
| `warden_audit.jsonl` | Flat audit log (append-only, current output) |
| `app/db.py` | `governance_events` table schema |

## Database Access
**Read-only.** Only query the `governance_events` table.

```sql
SELECT event_type, session_id, timestamp, payload
FROM governance_events
ORDER BY timestamp DESC
LIMIT 50;
```

Never query `hl7_messages`, `observations`, or any clinical table — that requires the Clinical Query Agent's full governance pipeline.

## What to Monitor
| Signal | Meaning |
|--------|---------|
| `INTENT_DENIED` events | Attempted blocked queries (admin, export, reset) |
| `TOOL_BLOCKED` events | Warden rejected a tool call |
| `SQL_REJECTED` events | SQL guard blocked a query |
| `PHI_REDACTION_FALLBACK` | Tokenizer missed a PHI field — investigate |
| High `GRANT_EXPIRED` rate | Agent taking too long between steps |
| Repeated `CLARIFICATION` tool use | Queries too ambiguous — consider improving intent classifier |

## Compliance Frameworks to Report Against
- **HIPAA Safe Harbor** — verify 6/18 identifiers are tokenized, never appear in audit logs
- **NIST AI RMF** — data minimization, intent validation coverage
- **Colorado AI Act** — reasonable care evidence (governance event volume, deny rate)
- **OWASP Agentic Top 10** — prompt injection attempts, tool call interception rate

## Audit Log Format (`warden_audit.jsonl`)
Each line is a JSON object — use `audit_safe_payload()` from `security_validation.py` before logging anything. PHI must never appear in audit output.

## Constraints
- Never call `llm_client.py` or `llm_gateway.py` with patient data
- Never write to `hl7_messages`, `observations`, `visits`, `medications`, or `diagnoses`
- Report outputs must pass `audit_safe_payload()` redaction before storage or display
- This agent has no session memory — each audit run is stateless
