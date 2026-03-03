#!/usr/bin/env bash
set -euo pipefail

# Entrypoint: run the Shiny app. Use gunicorn in production for robustness.
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}

if [ "${PRODUCTION:-0}" = "1" ]; then
  WEB_CONCURRENCY=${WEB_CONCURRENCY:-4}
  echo "Starting in production mode: gunicorn with ${WEB_CONCURRENCY} workers on ${HOST}:${PORT}"
  exec gunicorn -k uvicorn.workers.UvicornWorker -w "${WEB_CONCURRENCY}" "app:app" --bind "${HOST}:${PORT}" --timeout 120
else
  echo "Starting in development mode on ${HOST}:${PORT}"
  exec python app.py
fi
