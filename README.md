# Health Data Agent

Public demo: [healthdataagent.com](https://healthdataagent.com)

Health Data Agent is a healthcare interoperability and clinical AI demo. It parses HL7 v2 ORU messages, produces FHIR R4 resources, supports patient-data chat, and demonstrates Warden guardrails around AI workflows.

## Important Scope

This repository is suitable for a public portfolio demo using synthetic data. It is **not approved for real PHI, clinical decision-making, or a regulated production environment**. A real healthcare deployment still requires authentication, authorization, tenant and patient scoping, managed secrets, compliant infrastructure, audit retention, incident response, and formal security/privacy review.

## Features

- HL7 ORU parsing and validation
- FHIR R4 bundle generation
- Clinical observation review
- Patient dashboard and timeline
- Natural-language patient-data queries
- RAG-backed clinical references
- Warden request and tool guardrails

## Local Development

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.api:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The browser suites require Playwright:

```powershell
node tests/chat_frontend_browser_test.cjs
node tests/critical_banner_browser_test.cjs
```

## Production Demo Deployment

1. Copy `.env.example` to `.env`.
2. Set a unique `ADMIN_PASSWORD` with at least 16 characters.
3. Use an AWS IAM role with `bedrock:InvokeModel` access to the configured chat model and `amazon.titan-embed-text-v1`. Enable both models in Bedrock. Do not put AWS keys in the repository.
4. Keep `MESSAGE_RETENTION_DAYS=0` unless an explicit retention policy has been approved.
5. Leave `CORS_ALLOW_ORIGINS` empty for the same-origin Caddy deployment.
6. Run:

```bash
docker compose up --build -d
```

Caddy serves HTTPS on ports 80/443. Uvicorn is bound to loopback port 8080 for local diagnostics only.

Production Compose disables API documentation, runs the app as a non-root user, requires a non-demo reset password, adds health checks, and stores application and RAG SQLite data in named volumes.

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `agent.db` | SQLite database location |
| `AWS_REGION` | `us-east-1` | AWS Bedrock region |
| `BEDROCK_MODEL_ID` | Llama 3 8B | Bedrock chat model identifier |
| `ADMIN_PASSWORD` | none | Required for demo reset |
| `MESSAGE_RETENTION_DAYS` | `0` | Optional startup pruning; `0` disables it |
| `CORS_ALLOW_ORIGINS` | empty | Explicit comma-separated cross-origin allowlist |
| `ENABLE_API_DOCS` | `true` locally | Enables FastAPI docs; production Compose disables them |

## License

MIT License. Created by [Bradly Cheng](https://bradlycheng.com).
