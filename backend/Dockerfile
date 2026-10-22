# Optimized production Dockerfile for NexAgent Backend
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_DEFAULT_TIMEOUT=1000

WORKDIR /app

# Install minimal OS runtime dependencies (curl for healthchecks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -r requirements.txt

# Install Playwright Chromium browser, headless shell, and OS dependencies
RUN playwright install --with-deps chromium chromium-headless-shell

# Copy application source code
COPY . .

# Create runtime directories for data persistence and browser sessions
RUN mkdir -p /app/data /app/sessions

EXPOSE 8000

# Run FastAPI backend using Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
