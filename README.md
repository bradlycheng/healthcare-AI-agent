# Healthcare AI Agent 🏥

An intelligent interoperability agent that parses HL7 v2 ORU messages, standardizes them to FHIR R4, and uses a local LLM (Ollama) to generate clinical summaries.

## 🚀 Two Ways to Run

### 1. Local Demo Mode (Quick Start)
Perfect for development or local presentations.

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
2. **Setup AI**:
   Ensure [Ollama](https://ollama.com/) is running and you have the model:
   ```bash
   ollama pull llama3.2:3b
   ```
3. **Run App**:
   ```bash
   uvicorn app.api:app --reload
   ```
   Visit **http://localhost:8000** for the Landing Page and **http://localhost:8000/dashboard.html** for the Dashboard.

### 2. Cloud/Docker Mode (Staging)
Professional, containerized setup ready for AWS.

- **One-Command Start**:
  ```bash
  docker-compose up -d
  ```
- **Pull the AI Model** (Inside Docker):
  ```bash
  docker exec -it $(docker ps -qf "name=ollama") ollama pull llama3.2:3b
  ```
- **Configuration**:
  Modify environment variables in `docker-compose.yml` for custom database paths or AI endpoints.

---

## 🛠 Features

- **Ingestion**: Parses raw HL7 V2.5.1 ORU^R01 messages.
- **Conversion**: Transforms data into HL7 FHIR R4 Bundles.
- **AI Analysis**: Uses local LLM (Ollama) for clinical summaries. **PHI-Compliant**; data never leaves your infrastructure.
- **Interactive Dashboard**: Real-time monitoring of processed messages.

## 📁 Project Structure

- `app/`: Backend logic (FastAPI, parsing, AI client).
- `web/`: Frontend assets (Landing page, Dashboard).
- `agent.db`: Consolidated SQLite database (contains all sample data).
- `docker-compose.yml`: Production-ready orchestration.

## 🔒 Security (Demo Note)
For this demo, authentication is **DISABLED** to ensure a smooth viewing experience. If deploying to a public server, re-enable the `authenticate` logic in `app/api.py`.

## ⚙️ Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_PATH` | `agent.db` | Path to the SQLite DB |
| `OLLAMA_URL` | `http://localhost:11434/api/chat` | URL of the Ollama API |
