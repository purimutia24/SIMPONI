#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate
TEST_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/simponi-test.XXXXXX")"
cleanup() {
	if [[ -n "${UVICORN_PID:-}" ]]; then
		kill "$UVICORN_PID" 2>/dev/null || true
		wait "$UVICORN_PID" 2>/dev/null || true
	fi
	rm -rf -- "$TEST_TMP_DIR"
}
trap cleanup EXIT

TEST_DB="$TEST_TMP_DIR/simponi_test.db"
TEST_LOG="$TEST_TMP_DIR/uvicorn.log"
export DATABASE_URL="sqlite:///$TEST_DB"
TEST_PORT="$(venv/bin/python -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')"
export TEST_BASE_URL="http://127.0.0.1:$TEST_PORT"

uvicorn app.main:app --host 127.0.0.1 --port "$TEST_PORT" > "$TEST_LOG" 2>&1 &
UVICORN_PID=$!

for _ in {1..20}; do
	if venv/bin/python -c 'import os, urllib.request; urllib.request.urlopen(os.environ["TEST_BASE_URL"] + "/health", timeout=1)' 2>/dev/null; then
		break
	fi
	sleep 0.5
done
python3 test_full.py
