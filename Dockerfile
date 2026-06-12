# Use an official Python runtime as a parent image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy the application code and static files
COPY app/ ./app
COPY web/ ./web
COPY docs/ ./docs
COPY agent.db .
COPY entrypoint.sh .
COPY ingest_guidelines.py .
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data /app/vector_data \
    && chown -R appuser:appuser /app /data

# Expose the port the app runs on
EXPOSE 8080

# Environment variables with defaults
ENV DATABASE_PATH=agent.db
ENV AWS_REGION=us-east-1
ENV BEDROCK_MODEL_ID=meta.llama3-8b-instruct-v1:0
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5)"

# Run the app via entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
