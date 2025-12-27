# Healthcare AI Agent 🏥

An intelligent interoperability agent that parses HL7 v2 ORU messages, standardizes them to FHIR R4, and uses a local LLM (Ollama) to generate clinical summaries.

## Features

- **Ingestion**: Parses raw HL7 V2.5.1 ORU^R01 messages.
- **Conversion**: Transforms data into HL7 FHIR R4 Bundles (Patient + Observations).
- **AI Analysis**: Uses local LLM (Llama 3.2 via Ollama) to generate clinical summaries and flag abnormalities.
- **Live Demo UI**: Interactive web interface to test the pipeline.
- **API**: FastAPI backend for programmatic access.
- **Rate Limiting**: Protects local resources from overuse.

## Tech Stack

- **Backend**: Python 3.9+, FastAPI, SQLite, HL7apy
- **AI/LLM**: Ollama (running locally)
- **Frontend**: HTML5, Vanilla JS, CSS (Glassmorphism design)
- **Deployment**: Docker support included

## Quick Start

### Prerequisites

1. **Python 3.9+** installed.
2. **Ollama** installed and running.
   ```bash
   ollama pull llama3.2:3b
   ```

### Installation

1. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

Start the FastAPI server (calculates to `http://localhost:8000`):

```bash
uvicorn app.api:app --reload
```

Visit **http://localhost:8000** in your browser to see the landing page and try the **Live Demo**.

## API Endpoints

- `POST /oru/parse`: Parse HL7 text.
  - Body: `{ "hl7_text": "...", "use_llm": true }`
- `GET /messages`: List ingested messages.
- `GET /messages/{id}`: Get details for a specific message.

## Docker

Build and run the container:

```bash
docker build -t health-agent .
docker run -p 8080:8080 health-agent
```

(Note: For the Docker container to access host Ollama, you may need extra networking config, or set `OLLAMA_URL` env var to `http://host.docker.internal:11434/api/chat`).
