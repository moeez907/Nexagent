# Optimized production Dockerfile for NexAgent Backend with Native Chrome Desktop (noVNC)
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_DEFAULT_TIMEOUT=1000 \
    DISPLAY=:99

WORKDIR /app

# Install minimal OS runtime dependencies (curl, Xvfb, x11vnc, noVNC, websockify, openbox)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    xvfb \
    x11vnc \
    novnc \
    websockify \
    openbox \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install python packages
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=1000 --retries=10 -r requirements.txt

# Install Playwright Chromium browser, headless shell, and OS dependencies
RUN playwright install --with-deps chromium chromium-headless-shell

# Copy application source code
COPY . .

# Set executable permissions on entrypoint script
RUN chmod +x /app/entrypoint.sh

# Create runtime directories for data persistence and browser sessions
RUN mkdir -p /app/data /app/sessions

EXPOSE 8000 6080

# Run entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
