# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and static files
COPY app/ ./app
COPY web/ ./web
COPY agent.db .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Expose the port the app runs on
EXPOSE 8080

# Environment variables with defaults
ENV DATABASE_PATH=agent.db
ENV AWS_REGION=us-east-1
ENV BEDROCK_MODEL_ID=meta.llama3-8b-instruct-v1:0

# Run the app via entrypoint script
ENTRYPOINT ["./entrypoint.sh"]
