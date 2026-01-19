# Health Data Agent 🏥

**Live Demo**: [healthdataagent.com](https://healthdataagent.com)

An intelligent healthcare interoperability agent that parses HL7 v2 ORU messages, converts them to FHIR R4, and uses AWS Bedrock (Llama 3) to generate clinical summaries.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **HL7 Parsing** | Parses ORU^R01 messages with PID, OBR, OBX segments |
| **Input Validation** | Rejects invalid/malformed messages (non-ORU) with HTTP 400 |
| **ACK Generation** | Automatically generates HL7 v2 ACK (Acknowledgement) messages |
| **FHIR Conversion** | Generates FHIR R4 Bundles (Patient + Observation resources) |
| **AI Summaries** | AWS Bedrock LLM generates clinical summaries |
| **Natural Language Query**| Ask questions like "Show patients with high glucose" (SQL Gen) |
| **Web Dashboard** | Real-time monitoring of processed messages |
| **Rate Limiting** | 5-second cooldown between LLM requests |

## 🚀 Quick Start

### Prerequisites
1. **AWS Account** with Bedrock access enabled
2. **AWS Credentials** configured (`aws configure`)
3. **Bedrock Model Access**: Enable Llama 3 in AWS Console → Bedrock → Model access

### Local Development
```bash
pip install -r requirements.txt
aws configure  # Set region to us-east-1
uvicorn app.api:app --reload
```
Visit **http://localhost:8000**

### Docker (Recommended)
```bash
docker compose up -d
```
Visit **http://localhost:8080**

### Run Tests
```bash
python test_multiple_messages.py
```

## 📁 Project Structure

```
├── app/                  # Backend (FastAPI)
│   ├── api.py           # REST endpoints
│   ├── agent.py         # ORU pipeline logic
│   ├── hl7_parser.py    # HL7 message parsing
│   ├── fhir_builder.py  # FHIR Bundle generation
│   └── llm_client.py    # AWS Bedrock integration
├── web/                  # Frontend (HTML/CSS/JS)
├── agent.db             # SQLite database
├── docker-compose.yml   # Container orchestration
└── test_multiple_messages.py  # Integration tests
```

## 🔬 Supported HL7 Format

```
MSH|^~\&|LAB|HOSPITAL|EHR|CLINIC|202501170900||ORU^R01|MSG001|P|2.5
PID|1||123456^^^MRN||DOE^JOHN||19800101|M
OBR|1|||CBC_PANEL
OBX|1|NM|GLU^Glucose||105|mg/dL|70-100|H|||F
```

| Segment | Purpose |
|---------|---------|
| MSH | Message header |
| PID | Patient demographics |
| OBR | Order/panel info |
| OBX | Observation results (NM=numeric, TX=text) |

## ⚙️ Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock |
| `BEDROCK_MODEL_ID` | `meta.llama3-8b-instruct-v1:0` | LLM model |
| `DATABASE_PATH` | `agent.db` | SQLite database path |

## 🔒 Security Note

Authentication is **disabled** for demo purposes. For production, enable auth logic in `app/api.py`.

## 💰 Cost Estimate

| Resource | Cost |
|----------|------|
| EC2 (t2.micro) | Free Tier |
| Bedrock | ~$0.01 per message |
| **Monthly Total** | < $5 USD |

## 📄 License

MIT License - Created by [Bradly Cheng](https://bradlycheng.com)
