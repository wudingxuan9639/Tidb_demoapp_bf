#!/usr/bin/env bash

set -euo pipefail

if ! command -v tiup >/dev/null 2>&1; then
  echo "TiUP is not installed. See README.md for the installation command." >&2
  exit 1
fi

exec tiup playground v8.5.7 --tag demo-app
