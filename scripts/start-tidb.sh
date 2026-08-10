#!/usr/bin/env bash

set -euo pipefail

if ! command -v tiup >/dev/null 2>&1; then
  echo "TiUP is not installed. See README.md for the installation command." >&2
  exit 1
fi

tidb_version="${TIDB_VERSION:-v8.5.7}"
ready_timeout_seconds="${TIDB_READY_TIMEOUT_SECONDS:-30}"

is_listening() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

stop_playground() {
  if kill -0 "$playground_pid" >/dev/null 2>&1; then
    kill "$playground_pid" >/dev/null 2>&1 || true
    wait "$playground_pid" 2>/dev/null || true
  fi
}

tiup playground "$tidb_version" --tag demo-app &
playground_pid=$!
trap stop_playground INT TERM EXIT

for ((attempt = 1; attempt <= ready_timeout_seconds; attempt++)); do
  if ! kill -0 "$playground_pid" >/dev/null 2>&1; then
    echo "TiUP Playground exited before TiDB became ready. Review the terminal output above." >&2
    exit 1
  fi
  if is_listening 4000 && is_listening 20160; then
    echo "TiDB is ready: SQL 127.0.0.1:4000, TiKV 127.0.0.1:20160."
    break
  fi
  if ((attempt == ready_timeout_seconds)); then
    echo "TiDB did not become ready within ${ready_timeout_seconds} seconds. Both port 4000 (TiDB) and port 20160 (TiKV) must be listening." >&2
    echo "If TiKV repeatedly exits, inspect ~/Library/Logs/DiagnosticReports/tikv-server-*.ips. Do not reset ~/.tiup/data/demo-app unless you explicitly accept losing local TiDB data." >&2
    exit 1
  fi
  sleep 1
done

while kill -0 "$playground_pid" >/dev/null 2>&1; do
  sleep 2
  if ! is_listening 20160; then
    echo "TiKV on port 20160 stopped. Stopping the incomplete local cluster; restart after checking the TiKV crash report." >&2
    exit 1
  fi
done

wait "$playground_pid"
