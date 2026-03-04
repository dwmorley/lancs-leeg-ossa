#!/usr/bin/env bash
# ── Launch script for Mac / Linux ─────────────────────────────────────────────
# Pulls the latest release image and opens the app in Docker.
# Run once:  chmod +x launch.sh
# Then:      ./launch.sh

IMAGE="ghcr.io/dwmorley/lancs-leeg-ossa:latest"

# ── Local directories ─────────────────────────────────────────────────────────
# output/    → where the app saves result files (gpkg, csv, png …)
# user_data/ → put your input files here so the app can read them at /data
mkdir -p output user_data

echo "Pulling latest image …"
docker pull "$IMAGE"

echo "Starting app on http://localhost:8000  (Ctrl-C to stop)"
docker run --rm \
  -p 8000:8000 \
  -v "$(pwd)/output:/app/output" \
  -v "$(pwd)/user_data:/data" \
  "$IMAGE"
