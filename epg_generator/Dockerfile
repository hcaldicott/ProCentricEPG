FROM python:3.11-slim

# Install cron and other dependencies
RUN apt-get update && apt-get install -y \
    cron \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY src/ ./src/

# Create bundles directory
RUN mkdir -p /bundles

# Copy entrypoint script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Set environment variables with defaults
ENV CRON_SCHEDULE="0 0 * * *"
ENV TZ="UTC"

# Set the entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
