#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -d "/opt/homebrew/opt/openjdk" ]; then
  export JAVA_HOME="/opt/homebrew/opt/openjdk"
  export PATH="$JAVA_HOME/bin:$PATH"
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

"$PYTHON_BIN" server.py
