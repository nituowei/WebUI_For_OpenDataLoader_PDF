#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/pip install -U "opendataloader-pdf[hybrid]"

echo "Setup complete."
echo "Run ./run.sh and open http://127.0.0.1:8787"
