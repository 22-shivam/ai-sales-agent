# Dockerfile
FROM python:3.11-slim

# Install system dependencies
# portaudio is needed by some transitive deps (pyaudio)
# build-essential needed for compiling C extensions
RUN apt-get update && apt-get install -y \
    portaudio19-dev \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Expose port for webhook server
EXPOSE 8000

# Start the main server (handles webhooks + orchestrator)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", $PORT]
