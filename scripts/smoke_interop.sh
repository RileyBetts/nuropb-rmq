#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean ↔ Python interop smokes. Needs RabbitMQ + lake + uv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if command -v uv >/dev/null 2>&1; then
  PY=(uv run python)
else
  PY=(python)
fi

export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
export NUROPB_RMQ_PORT="${NUROPB_RMQ_PORT:-5672}"

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "FAIL ${label}: missing '${needle}'" >&2
    echo "$haystack" >&2
    return 1
  fi
}

kill_bg() {
  local pid="$1"
  if kill -0 "$pid" 2>/dev/null; then
    kill -INT "$pid" 2>/dev/null || true
    sleep 0.3
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

# Python consumer + Lean publisher
log="$(mktemp)"
"${PY[@]}" examples/interop_hello/consumer.py >"$log" 2>&1 &
pid=$!
sleep 1
out="$(lake exe interop_hello_publisher 2>&1)"
sleep 0.5
kill_bg "$pid"
assert_contains "interop_hello lean→py pub" "$out" "hello-nuropb-rmq"
assert_contains "interop_hello lean→py cons" "$(cat "$log")" "hello-nuropb-rmq"
rm -f "$log"
echo "PASS interop_hello lean publisher / python consumer"

# Lean consumer + Python publisher
log="$(mktemp)"
lake exe interop_hello_consumer >"$log" 2>&1 &
pid=$!
sleep 1
out="$("${PY[@]}" examples/interop_hello/publisher.py 2>&1)"
sleep 1
kill_bg "$pid"
assert_contains "interop_hello py→lean pub" "$out" "hello-nuropb-rmq"
assert_contains "interop_hello py→lean cons" "$(cat "$log")" "hello-nuropb-rmq"
rm -f "$log"
echo "PASS interop_hello python publisher / lean consumer"

# Python service + Lean client
slog="$(mktemp)"
"${PY[@]}" examples/interop_mesh/service.py >"$slog" 2>&1 &
pid=$!
sleep 2
clout="$(lake exe interop_mesh_client 2>&1)" || true
sleep 0.3
kill_bg "$pid"
assert_contains "interop_mesh lean client" "$clout" "interop.ping"
assert_contains "interop_mesh lean client" "$clout" "[client] done"
rm -f "$slog"
echo "PASS interop_mesh python service / lean client"

# Lean service + Python client
slog="$(mktemp)"
lake exe interop_mesh_service >"$slog" 2>&1 &
pid=$!
sleep 2
clout="$("${PY[@]}" examples/interop_mesh/client.py 2>&1)" || true
sleep 0.3
kill_bg "$pid"
assert_contains "interop_mesh python client" "$clout" "interop.ping"
assert_contains "interop_mesh python client" "$clout" "[client] done"
rm -f "$slog"
echo "PASS interop_mesh lean service / python client"

echo "All interop smokes passed."
