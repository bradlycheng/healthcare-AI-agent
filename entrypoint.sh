#!/bin/bash
# entrypoint.sh - Initialize database if needed

# If DATABASE_PATH is set to /data/agent.db but file doesn't exist,
# copy the seed database from /app/agent.db
if [ "$DATABASE_PATH" = "/data/agent.db" ] && [ ! -f /data/agent.db ]; then
    echo "Initializing database at /data/agent.db from seed data..."
    cp /app/agent.db /data/agent.db
    echo "Database initialized successfully"
fi

# Start the application
exec uvicorn app.api:app --host 0.0.0.0 --port 8080
