#!/usr/bin/env bash
# run_dev.sh - start/stop/status development servers for the dashboard
# Usage: ./scripts/run_dev.sh start|stop|status

set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

start_backend() {
  if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat $BACKEND_PID_FILE)" 2>/dev/null; then
    echo "Backend already running (PID=$(cat $BACKEND_PID_FILE))"
    return
  fi
  echo "Starting backend (uvicorn)..."
  # Use python -m uvicorn so it works even if uvicorn not on PATH
  nohup python3 -m uvicorn dashboard.backend.main:app --reload --port 8000 \
    > "$LOG_DIR/backend.log" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
  disown
  echo "Backend started, log: $LOG_DIR/backend.log"
}

start_frontend() {
  if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat $FRONTEND_PID_FILE)" 2>/dev/null; then
    echo "Frontend already running (PID=$(cat $FRONTEND_PID_FILE))"
    return
  fi
  echo "Starting frontend server on http://localhost:8080 ..."
  # Prefer livereload if available so the browser reloads when frontend files change
  if python3 - <<'PY' >/dev/null 2>&1
try:
    import livereload
    print('ok')
except Exception:
    raise SystemExit(2)
PY
  then
    echo "livereload available -> using it to serve frontend"
    nohup python3 -m livereload "$ROOT_DIR/dashboard/frontend" --port 8080 \
      > "$LOG_DIR/frontend.log" 2>&1 &
  else
    echo "livereload not available -> falling back to simple HTTP server"
    nohup bash -c "cd '$ROOT_DIR/dashboard/frontend' && python3 -m http.server 8080" \
      > "$LOG_DIR/frontend.log" 2>&1 &
  fi
  echo $! > "$FRONTEND_PID_FILE"
  disown
  echo "Frontend started, log: $LOG_DIR/frontend.log"
}

stop_backend() {
  if [ -f "$BACKEND_PID_FILE" ]; then
    pid=$(cat "$BACKEND_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping backend PID=$pid"
      kill "$pid" && rm -f "$BACKEND_PID_FILE"
      return
    fi
    rm -f "$BACKEND_PID_FILE"
  fi
  echo "Backend not running"
}

stop_frontend() {
  if [ -f "$FRONTEND_PID_FILE" ]; then
    pid=$(cat "$FRONTEND_PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping frontend PID=$pid"
      kill "$pid" && rm -f "$FRONTEND_PID_FILE"
      return
    fi
    rm -f "$FRONTEND_PID_FILE"
  fi
  echo "Frontend not running"
}

status() {
  if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat $BACKEND_PID_FILE)" 2>/dev/null; then
    echo "Backend running (PID=$(cat $BACKEND_PID_FILE))"
  else
    echo "Backend not running"
  fi
  if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat $FRONTEND_PID_FILE)" 2>/dev/null; then
    echo "Frontend running (PID=$(cat $FRONTEND_PID_FILE))"
  else
    echo "Frontend not running"
  fi
}

case "${1:-}" in
  start)
    start_backend
    start_frontend
    echo "Dev servers started. Open http://localhost:8080 in your browser."
    ;;
  stop)
    stop_frontend
    stop_backend
    echo "Dev servers stopped."
    ;;
  restart)
    $0 stop
    sleep 1
    $0 start
    ;;
  status)
    status
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    exit 2
    ;;
esac
