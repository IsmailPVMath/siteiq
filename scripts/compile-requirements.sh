#!/usr/bin/env bash
# Regenerate requirements.txt (pinned lock) from requirements.in.
# Run from repo root: ./scripts/compile-requirements.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv-lock ]]; then
  python3 -m venv .venv-lock
  .venv-lock/bin/pip install -U pip pip-tools wheel
fi

.venv-lock/bin/pip-compile \
  --resolver=backtracking \
  --strip-extras \
  --output-file=requirements.txt \
  requirements.in

echo "Updated requirements.txt — review and commit both requirements.in and requirements.txt."
