# Clinical Query Agent

## Role
Answer natural language clinical questions using a ReAct loop over SQL, RAG, and calculators. Governed by intent classification and capability grants.

## Entry Points
| File | Purpose |
|------|---------|
| `app/healthcare_agent.py` | ReAct loop — main agent logic |
| `app/llm_gateway.py` | Governed LLM access (use this, never llm_client directly) |
| `app/intent_classifier.py` | Classify + validate query intent before any tool call |
| `app/grant_builder.py` | Build capability grant from intent (5-min TTL) |
| `app/sql_guard.py` | Whitelist SQL before execution |
| `app/token_guard.py` | PHI tokenization (IN) / detokenization (OUT) |
| `app/safe_memory.py` | Conversation state (30-min TTL, injection-resistant) |
| `app/reference_resolver.py` | Validate references to prior answers |
| `app/warden.py` | Policy enforcement — wraps all tool calls |

## API Endpoint Owned
- `POST /api/query` — accepts `{ question, session_id }`, returns `AgentResponse`

## Available Tools
| Tool | Purpose |
|------|---------|
| `query_database` | NL → SQL over whitelisted tables |
| `search_guidelines` | RAG over ChromaDB clinical guidelines |
| `get_patient_context` | Patient history and lab trends |
| `clinical_calculator` | BMI, eGFR, risk scores |
| `ask_clarification` | Handle ambiguous queries |

## SQL Whitelist
**Allowed tables**: `hl7_messages`, `observations`, `visits`, `medications`, `diagnoses`
**Blocked**: DROP, DELETE, INSERT, UPDATE, ALTER, EXEC, subqueries, `contacts` table

## Intent DENY List
Reject immediately — do not proceed to tool calls:
`admin`, `delete`, `export`, `reset`, `policy_override`, `system_prompt_request`, `hidden_instruction_execution`

## Reasoning Modes
- `standard` — ReAct loop (default)
- `deep` — reflection + planning + ReAct (slower, more thorough)

## Response Shape (`AgentResponse`)
```python
{
  answer: str,
  success: bool,
  reasoning_trace: list,
  tools_used: list,
  sources: list,
  sql: str | None,
  row_count: int | None
}
```

## Constraints
- Max rows returned: **50** (hard cap: 200) — enforced by grant builder
- Rate limit: **5-second cooldown** between LLM calls
- PHI must be tokenized before reaching LLM — never pass raw names/IDs/DOBs
- Token maps are request-scoped — carry via `safe_metadata`, never cache across requests
- Grants expire after **5 minutes** — never cache a grant object
- Max conversation state: 25 patient IDs, 20 topic codes, 25 result IDs
