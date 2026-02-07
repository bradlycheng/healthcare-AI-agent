#!/bin/bash
# entrypoint.sh - Initialize database and RAG if needed

# If DATABASE_PATH is set to /data/agent.db but file doesn't exist,
# copy the seed database from /app/agent.db
if [ "$DATABASE_PATH" = "/data/agent.db" ] && [ ! -f /data/agent.db ]; then
    echo "Initializing database at /data/agent.db from seed data..."
    cp /app/agent.db /data/agent.db
    echo "Database initialized successfully"
fi

# Initialize RAG vector store if it doesn't exist
if [ ! -d "/app/chroma_db" ] || [ -z "$(ls -A /app/chroma_db 2>/dev/null)" ]; then
    echo "Initializing RAG vector store..."
    python ingest_guidelines.py || echo "Warning: RAG indexing failed, continuing anyway"
    echo "RAG initialization complete"
fi

# Start the application or run passed command
if [ $# -eq 0 ]; then
    exec uvicorn app.api:app --host 0.0.0.0 --port 8080
else
    exec "$@"
fi
