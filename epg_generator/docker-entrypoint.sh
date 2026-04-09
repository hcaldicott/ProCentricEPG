#!/bin/bash
set -e

# Log function
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Resolve Python interpreter once so cron does not depend on PATH.
resolve_python_bin() {
    if command -v python3 >/dev/null 2>&1; then
        echo "$(command -v python3)"
    elif command -v python >/dev/null 2>&1; then
        echo "$(command -v python)"
    else
        log "ERROR: No Python interpreter found (python3/python)"
        exit 1
    fi
}

PYTHON_BIN="$(resolve_python_bin)"
log "Using Python interpreter: ${PYTHON_BIN}"

# Function to run the EPG generation script
run_epg_generation() {
    log "Starting EPG bundle generation..."
    cd /app/src
    "${PYTHON_BIN}" main.py
    if [ $? -eq 0 ]; then
        log "EPG bundle generation completed successfully"
    else
        log "ERROR: EPG bundle generation failed"
    fi
}

# If RUN_ONCE is set, run immediately and exit
if [ "${RUN_ONCE}" = "true" ]; then
    log "RUN_ONCE mode enabled - running EPG generation immediately"
    run_epg_generation
    log "Exiting after single run"
    exit 0
fi

# Set up cron job
log "Setting up cron schedule: ${CRON_SCHEDULE}"

# Create cron job file
echo "${CRON_SCHEDULE} cd /app/src && ${PYTHON_BIN} main.py >> /proc/1/fd/1 2>&1" > /etc/cron.d/epg-cron

# Give execution rights on the cron job
chmod 0644 /etc/cron.d/epg-cron

# Apply cron job
crontab /etc/cron.d/epg-cron

# Create the log file to be able to run tail
touch /var/log/cron.log

log "Cron job configured. Running initial EPG generation..."

# Run the script once on startup
run_epg_generation

log "Starting cron daemon..."

# Start cron in foreground
cron && tail -f /var/log/cron.log
