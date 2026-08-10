#!/usr/bin/env bash

set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend_dir="$project_root/frontend"

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is not installed. Install a supported Node.js version first." >&2
  exit 1
fi

cd "$frontend_dir"

if [[ ! -d node_modules ]]; then
  npm ci
fi

exec npm run dev
