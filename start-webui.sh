#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

PORT="${ODL_WEBUI_PORT:-8787}"
URL="http://127.0.0.1:${PORT}/"
PID_FILE=".webui.pid"
LOG_FILE="webui.log"

is_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

if [ -f "$PID_FILE" ]; then
  pid="$(cat "$PID_FILE")"
  if is_running "$pid"; then
    echo "ODL PDF WebUI is already running at ${URL} (pid ${pid})."
    if [ "${ODL_WEBUI_NO_OPEN:-0}" != "1" ]; then
      open "$URL"
    fi
    exit 0
  fi
fi

if curl -fsS "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
  echo "Port ${PORT} already has a running WebUI. Opening ${URL}."
  if [ "${ODL_WEBUI_NO_OPEN:-0}" != "1" ]; then
    open "$URL"
  fi
  exit 0
fi

ODL_WEBUI_NO_BROWSER=1 ODL_WEBUI_PORT="$PORT" nohup ./run.sh >"$LOG_FILE" 2>&1 &
pid="$!"
echo "$pid" > "$PID_FILE"

for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/status" >/dev/null 2>&1; then
    echo "ODL PDF WebUI started at ${URL} (pid ${pid})."
    if [ "${ODL_WEBUI_NO_OPEN:-0}" != "1" ]; then
      open "$URL"
    fi
    exit 0
  fi
  sleep 0.2
done

echo "WebUI did not become ready. Check ${LOG_FILE}."
exit 1

