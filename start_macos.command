#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec python3 -m uvicorn app_macos.main:app --reload --host 0.0.0.0 --port 8000

