# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY app/ ./app
COPY web/ ./web
COPY agent.db . 
# Note: In production you might want to use a volume for the DB, or a real DB service.

# Expose the port the app runs on
EXPOSE 8080

# Define environment variable
ENV PORT=8080

# Run app.py when the container launches
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]
