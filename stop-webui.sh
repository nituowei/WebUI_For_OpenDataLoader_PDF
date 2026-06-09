#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PORT="${ODL_WEBUI_PORT:-8787}"
PID_FILE=".webui.pid"

stop_pid() {
  local pid="$1"
  if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    return 1
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 25); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done
  kill -9 "$pid" 2>/dev/null || true
}

if curl -fsS -X POST "http://127.0.0.1:${PORT}/api/shutdown" -H "Content-Type: application/json" -d '{}' >/dev/null 2>&1; then
  rm -f "$PID_FILE"
  echo "ODL PDF WebUI stopped via API."
  exit 0
fi

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if stop_pid "$pid"; then
    rm -f "$PID_FILE"
    echo "ODL PDF WebUI stopped (pid ${pid})."
    exit 0
  fi
fi

port_pid="$(lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
if [ -n "$port_pid" ] && stop_pid "$port_pid"; then
  rm -f "$PID_FILE"
  echo "Stopped process listening on port ${PORT} (pid ${port_pid})."
  exit 0
fi

rm -f "$PID_FILE"
echo "ODL PDF WebUI is not running."

