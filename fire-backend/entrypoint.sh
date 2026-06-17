#!/bin/sh
set -e

LOG_FILE=${LOG_FILE:-/var/log/fire-backend/application.log}
LOG_DIR=$(dirname "$LOG_FILE")

if [ ! -d "$LOG_DIR" ]; then
  mkdir -p "$LOG_DIR" || true
fi

if id "appuser" >/dev/null 2>&1; then
  chown -R appuser:appuser "$LOG_DIR" || true
fi

exec java -jar /app/app.jar "$@"
