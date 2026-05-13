#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
mkdir -p data
export PYTHONPATH=.
python scripts/seed_workspace.py
python -m uvicorn app.main:app --host "${AGENTBRIDGE_HOST:-127.0.0.1}" --port "${AGENTBRIDGE_PORT:-8000}" --reload
