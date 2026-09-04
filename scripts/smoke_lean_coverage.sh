#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean IO coverage smokes (PLAIN). Needs RabbitMQ + lake. Not default lake build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
export NUROPB_RMQ_PORT="${NUROPB_RMQ_PORT:-5672}"

BIN="$ROOT/.lake/build/bin"
lake build lean_hello_publisher lean_hello_consumer \
  lean_mesh_service lean_mesh_client \
  lean_claims_service lean_claims_client \
  lean_events_hello lean_dlq_hello lean_reconnect_client >/dev/null

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

clog="$(mktemp)"
"$BIN/lean_hello_consumer" >"$clog" 2>&1 &
cpid=$!
sleep 2
pout="$("$BIN/lean_hello_publisher" 2>&1)"
sleep 1
kill_bg "$cpid"
assert_contains "lean_hello pub" "$pout" "hello-nuropb-rmq"
assert_contains "lean_hello cons" "$(cat "$clog")" "hello-nuropb-rmq"
rm -f "$clog"
echo "PASS lean_hello"

slog="$(mktemp)"
"$BIN/lean_mesh_service" >"$slog" 2>&1 &
spid=$!
sleep 3
mout="$("$BIN/lean_mesh_client" 2>&1)" || true
sleep 0.3
assert_contains "lean_mesh" "$mout" "demo.ping"
assert_contains "lean_mesh" "$mout" "[client] done"

rout="$("$BIN/lean_reconnect_client" 2>&1)" || true
assert_contains "lean_reconnect" "$rout" "reconnect: ok"
kill_bg "$spid"
rm -f "$slog"
echo "PASS lean_mesh + reconnect"

cs="$(mktemp)"
"$BIN/lean_claims_service" >"$cs" 2>&1 &
cpid=$!
sleep 5
cout="$("$BIN/lean_claims_client" 2>&1)" || true
if [[ "$cout" != *"claims: ok"* ]]; then
  echo "claims service log:" >&2
  cat "$cs" >&2
fi
kill_bg "$cpid"
assert_contains "lean_claims" "$cout" "claims: ok"
rm -f "$cs"
echo "PASS lean_claims"

eout="$("$BIN/lean_events_hello" 2>&1)"
assert_contains "lean_events" "$eout" "events: ok"
echo "PASS lean_events"

dout="$("$BIN/lean_dlq_hello" 2>&1)"
assert_contains "lean_dlq" "$dout" "dlq: ok"
echo "PASS lean_dlq"

echo "All Lean coverage smokes passed."
