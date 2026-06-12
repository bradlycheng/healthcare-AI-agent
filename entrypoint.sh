#!/bin/bash
# entrypoint.sh - Initialize database and RAG if needed

# If DATABASE_PATH is set to /data/agent.db but file doesn't exist,
# copy the seed database from /app/agent.db
if [ "$DATABASE_PATH" = "/data/agent.db" ] && [ ! -f /data/agent.db ]; then
    echo "Initializing database at /data/agent.db from seed data..."
    cp /app/agent.db /data/agent.db
    echo "Database initialized successfully"
fi

# Initialize the embedded RAG vector store if it doesn't exist
if [ ! -f "/app/vector_data/vectors.sqlite3" ]; then
    echo "Initializing RAG vector store..."
    if python ingest_guidelines.py; then
        echo "RAG initialization complete"
    else
        echo "Warning: RAG indexing failed; starting without guideline retrieval"
    fi
fi

# Start the application or run passed command
if [ $# -eq 0 ]; then
    # The app port is exposed only to localhost and Caddy in Compose.
    # Trust Caddy's forwarded client IP so per-IP rate limits do not collapse
    # all public visitors into the proxy container address.
    exec uvicorn app.api:app --host 0.0.0.0 --port 8080 \
        --proxy-headers --forwarded-allow-ips="*"
else
    exec "$@"
fi
