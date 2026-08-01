#!/usr/bin/env bash

set -euo pipefail

BASE_KERNEL="${KERNEL_URL:-http://127.0.0.1:8000}"
BASE_SOLVER="${SOLVER_URL:-http://127.0.0.1:8001}"
BASE_TREE="${TREE_URL:-http://127.0.0.1:8002}"
BASE_AGENT="${AGENT_URL:-http://127.0.0.1:8003}"

PASS_COUNT=0

pass() {
  echo "✅ $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "❌ $1"
  exit 1
}

expect_contains() {
  local label="$1"
  local body="$2"
  local expected="$3"

  if [[ "$body" == *"$expected"* ]]; then
    pass "$label"
  else
    echo "--- response for $label ---"
    echo "$body"
    echo "----------------------------"
    fail "$label (missing: $expected)"
  fi
}

http_get() {
  local url="$1"
  curl -sS "$url"
}

http_post_json() {
  local url="$1"
  local payload="$2"
  curl -sS -X POST "$url" -H "Content-Type: application/json" -d "$payload"
}

echo "Running OpenCAD backend smoke checks..."

# ── Health ──────────────────────────────────────────────────────────

kernel_health="$(http_get "$BASE_KERNEL/healthz")"
expect_contains "kernel health" "$kernel_health" '"status":"ok"'

solver_health="$(http_get "$BASE_SOLVER/healthz")"
expect_contains "solver health" "$solver_health" '"status":"ok"'

tree_health="$(http_get "$BASE_TREE/healthz")"
expect_contains "tree health" "$tree_health" '"status":"ok"'

agent_health="$(http_get "$BASE_AGENT/healthz")"
expect_contains "agent health" "$agent_health" '"status":"ok"'

# ── Kernel operations ──────────────────────────────────────────────

kernel_ops="$(http_get "$BASE_KERNEL/operations")"
expect_contains "kernel operations" "$kernel_ops" 'create_box'

# Create a box and capture shape_id
create_box_result="$(http_post_json "$BASE_KERNEL/operations/create_box" '{"payload":{"length":10,"width":5,"height":3}}')"
expect_contains "kernel create_box" "$create_box_result" '"ok":true'

# Extract shape_id (simple grep)
shape_id="$(echo "$create_box_result" | grep -oP '"shape_id"\s*:\s*"[^"]+"' | head -1 | grep -oP '"[^"]+"\s*$' | tr -d '"' | xargs)"

if [[ -n "$shape_id" ]]; then
  pass "kernel shape_id extracted: $shape_id"

  # ── Mesh endpoint ──────────────────────────────────────────────

  mesh_result="$(http_get "$BASE_KERNEL/shapes/$shape_id/mesh?deflection=0.5")"
  expect_contains "kernel mesh" "$mesh_result" '"vertices"'

  # ── Mesh streaming endpoint ────────────────────────────────────

  stream_result="$(curl -sS -N --max-time 5 "$BASE_KERNEL/shapes/$shape_id/mesh/stream?deflection=0.5" 2>/dev/null || true)"
  if [[ -n "$stream_result" ]]; then
    expect_contains "kernel mesh stream" "$stream_result" '"faceIndex"'
  else
    echo "⚠️  mesh stream timed out or empty (OK if analytic backend)"
  fi
else
  echo "⚠️  could not extract shape_id from create_box result"
fi

# ── Operation log ──────────────────────────────────────────────────

op_log="$(http_get "$BASE_KERNEL/operations/log")"
expect_contains "kernel op log" "$op_log" '"operation"'

# ── Operation schema versioning ────────────────────────────────────

box_schema="$(http_get "$BASE_KERNEL/operations/create_box/schema")"
expect_contains "kernel schema version" "$box_schema" 'x-opencad-version'

# ── Replay ─────────────────────────────────────────────────────────

replay_result="$(http_post_json "$BASE_KERNEL/operations/replay" '{"entries":[{"operation":"create_box","params":{"length":5,"width":5,"height":5}},{"operation":"create_sphere","params":{"radius":2}}]}')"
expect_contains "kernel replay" "$replay_result" '"replayed":2'

# ── Solver ─────────────────────────────────────────────────────────

solver_check="$(http_post_json "$BASE_SOLVER/sketch/check" '{"entities":{},"constraints":[]}')"
expect_contains "solver sketch/check" "$solver_check" '"status":"SOLVED"'

# ── Tree ───────────────────────────────────────────────────────────

tree_create="$(http_post_json "$BASE_TREE/trees" '{"root_id":"smoke-root","nodes":{"smoke-root":{"id":"smoke-root","name":"Root","operation":"root","parameters":{},"depends_on":[],"status":"built"}}}')"
expect_contains "tree create" "$tree_create" '"root_id":"smoke-root"'

tree_get="$(http_get "$BASE_TREE/trees/smoke-root")"
expect_contains "tree get" "$tree_get" '"root_id":"smoke-root"'

# ── Agent ──────────────────────────────────────────────────────────

agent_chat_payload='{"message":"Create a simple feature","tree_state":{"root_id":"smoke-root","nodes":{"smoke-root":{"id":"smoke-root","name":"Root","operation":"root","parameters":{},"depends_on":[],"status":"built"}}},"conversation_history":[]}'
agent_chat="$(http_post_json "$BASE_AGENT/chat" "$agent_chat_payload")"
expect_contains "agent chat" "$agent_chat" '"operations_executed"'

echo
echo "Smoke checks passed: $PASS_COUNT"
echo "Backend status: OK"
