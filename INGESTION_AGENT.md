# Ingestion Agent

## Role
Parse inbound HL7 v2 ORU messages, convert to FHIR R4, persist to SQLite. Stateless — no conversation memory, no LLM calls.

## Entry Points
| File | Purpose |
|------|---------|
| `app/agent.py` | Main pipeline: validate → parse → FHIR → summarize → store |
| `app/hl7_parser.py` | HL7 v2.5.1 parsing (MSH/PID/OBR/OBX/NTE segments) |
| `app/fhir_builder.py` | FHIR R4 Bundle generation |
| `app/hl7_guard.py` | Input validation — run this FIRST before any parsing |
| `app/llm_gateway.py` | Clinical summary generation (only call for TX/FT/ED/ST obs types) |
| `app/db.py` | Persistence layer |

## API Endpoints Owned
- `POST /oru/parse` — parse + return FHIR bundle (stores parse session, 10-min TTL)
- `POST /messages` — persist parsed result to DB

## Constraints
- Only accept `ORU^R01` message type — reject all others with HTTP 400
- Always run `hl7_guard.py` before parsing — never skip validation
- Parse sessions have a **10-minute TTL** before persistence is allowed
- `SECURITY_ALLOW_ORU_DIRECT_PERSIST=false` by default — respect it
- LLM calls only for text observation types (TX, FT, ED, ST) — not numeric (NM)
- Do not call `llm_client.py` directly — route through `llm_gateway.py`

## Supported HL7 Segments
| Segment | Purpose |
|---------|---------|
| MSH | Message header + type validation |
| PID | Patient demographics |
| OBR | Order/panel info |
| OBX | Observations (NM=numeric, TX=text) |
| NTE | Attached notes |

## Output
- FHIR R4 Bundle (Patient + Observation resources)
- HL7 ACK message
- Clinical summary (if text observations present)
- Persisted row in `hl7_messages` + `observations` tables
