#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p .dashboard-logs

echo "Starting backend on http://localhost:8000..."
nohup uv run uvicorn dashboard.backend.main:app --reload --port 8000 > .dashboard-logs/backend.log 2>&1 &

echo "Starting frontend on http://localhost:8080..."
nohup python3 -m http.server 8080 --directory dashboard/frontend > .dashboard-logs/frontend.log 2>&1 &

sleep 3

if curl -s http://localhost:8000/health >/dev/null; then
  echo "Dashboard is ready."
  echo "Open: http://localhost:8080/index.html"
else
  echo "Backend did not become ready yet. Check .dashboard-logs/backend.log"
  exit 1
fi
