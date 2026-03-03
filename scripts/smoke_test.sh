#!/usr/bin/env bash
set -euo pipefail

HOST=${1:-localhost}
PORT=${2:-8000}

echo "Checking http://${HOST}:${PORT}/"
for i in {1..10}; do
  if curl -sSf "http://${HOST}:${PORT}/" >/dev/null 2>&1; then
    echo "OK: http://${HOST}:${PORT}/ returned 200"
    exit 0
  fi
  echo "Waiting for service... (${i}/10)"
  sleep 2
done

echo "ERROR: service did not become healthy"
exit 2
