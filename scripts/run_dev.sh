#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/apps/backend"
FRONTEND_DIR="$ROOT_DIR/apps/opencad_viewport"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
OPENCAD_TREE_LIVE_KERNEL="${OPENCAD_TREE_LIVE_KERNEL:-true}"
OPENCAD_KERNEL_URL="${OPENCAD_KERNEL_URL:-http://$BACKEND_HOST:$BACKEND_PORT/kernel}"

export OPENCAD_TREE_LIVE_KERNEL OPENCAD_KERNEL_URL

if [[ ! -d "$BACKEND_DIR" ]]; then
  echo "Backend directory not found: $BACKEND_DIR" >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR" ]]; then
  echo "Frontend directory not found: $FRONTEND_DIR" >&2
  exit 1
fi

backend_pid=""
frontend_pid=""

cleanup() {
  local exit_code=$?

  if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" 2>/dev/null; then
    kill "$backend_pid" 2>/dev/null || true
  fi

  if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" 2>/dev/null; then
    kill "$frontend_pid" 2>/dev/null || true
  fi

  wait "$backend_pid" "$frontend_pid" 2>/dev/null || true
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

echo "Starting backend on http://$BACKEND_HOST:$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  uv run --extra server --extra occt python -m uvicorn api:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
backend_pid=$!

echo "Starting frontend on http://$FRONTEND_HOST:$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  pnpm dev --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
) &
frontend_pid=$!

echo "Backend PID: $backend_pid"
echo "Frontend PID: $frontend_pid"
echo "Press Ctrl+C to stop both services."

wait -n "$backend_pid" "$frontend_pid"
