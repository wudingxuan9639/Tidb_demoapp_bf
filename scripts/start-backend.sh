#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
backend_dir="$project_root/backend"
venv_python="$backend_dir/.venv/bin/python"

if [[ ! -x "$venv_python" ]]; then
  echo "Python virtual environment is missing. Run: cd backend && python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt" >&2
  exit 1
fi

if [[ ! -f "$backend_dir/.env" ]]; then
  cp "$backend_dir/.env.example" "$backend_dir/.env"
  echo "Created backend/.env from .env.example."
fi

cd "$backend_dir"
exec "$venv_python" -m uvicorn app.main:app --host 127.0.0.1 --port 8800 --reload
