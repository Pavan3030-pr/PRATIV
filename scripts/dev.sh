#!/usr/bin/env bash
# Local development for the explorer UI and the agent API.
#   ./scripts/dev.sh      -> agent on :8000, explorer on :5173
# The full stack (PostgreSQL + Spring Boot + agent + UI) is `docker compose up --build`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install -q --disable-pip-version-check -r agent/requirements.txt

if [ ! -d frontend/node_modules ]; then
  ( cd frontend && npm ci )
fi

cleanup() {
  [ -n "${AGENT_PID:-}" ] && kill "$AGENT_PID" 2>/dev/null || true
  [ -n "${WEB_PID:-}" ] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

( cd agent && exec ../.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 ) &
AGENT_PID=$!
( cd frontend && exec npm run dev -- --host 127.0.0.1 --port 5173 ) &
WEB_PID=$!

echo "Agent API: http://127.0.0.1:8000/docs"
echo "Explorer:  http://127.0.0.1:5173/#/explore"
wait
