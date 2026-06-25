#!/usr/bin/env bash
# Local FastAPI dev server (Streamlit app unchanged on :8501)
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)"
exec python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
