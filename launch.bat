@echo off
REM ── Launch script for Windows ─────────────────────────────────────────────
REM Pulls the latest release image and opens the app in Docker.
REM Requires Docker Desktop to be running.
REM Double-click this file to launch the app.

SET IMAGE=ghcr.io/dwmorley/lancs-leeg-ossa:latest

REM ── Create local directories if they don't exist  ─────────────────────────
if not exist output   mkdir output

echo Pulling latest image ...
docker pull %IMAGE%

echo.
echo Starting app on http://localhost:8000
echo Close this window to stop the app.
echo.
docker run --rm ^
  -p 8000:8000 ^
  -v "%cd%\output:/app/output" ^
  %IMAGE%
