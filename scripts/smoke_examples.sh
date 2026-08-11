#!/usr/bin/env bash
# Smoke-run all example suites against local RabbitMQ.
# Usage: ./scripts/smoke_examples.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck source=/dev/null
  source .venv/bin/activate
fi

export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"

resolve_port() {
  if [[ -n "${NUROPB_RMQ_PORT:-}" ]]; then
    echo "$NUROPB_RMQ_PORT"
    return
  fi
  local p
  for p in 5672 5673; do
    if (echo >/dev/tcp/"$NUROPB_RMQ_HOST"/"$p") >/dev/null 2>&1; then
      echo "$p"
      return
    fi
  done
  echo "RabbitMQ not listening on ${NUROPB_RMQ_HOST}:5672 or 5673" >&2
  exit 1
}

export NUROPB_RMQ_PORT
NUROPB_RMQ_PORT="$(resolve_port)"
echo "Using AMQP ${NUROPB_RMQ_HOST}:${NUROPB_RMQ_PORT}"

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo "FAIL ${label}: missing '${needle}'" >&2
    echo "----- output -----" >&2
    echo "$haystack" >&2
    echo "------------------" >&2
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

pass_suite() {
  echo "PASS $1"
}

# --- vanilla_hello ---
smoke_hello() {
  local log peer_out
  log="$(mktemp)"
  python examples/vanilla_hello/consumer.py >"$log" 2>&1 &
  local pid=$!
  sleep 0.8
  peer_out="$(python examples/vanilla_hello/publisher.py 2>&1)"
  sleep 0.4
  kill_bg "$pid"
  local cons
  cons="$(cat "$log")"
  rm -f "$log"
  assert_contains "vanilla_hello/publisher" "$peer_out" "sent b'hello-nuropb-rmq'"
  assert_contains "vanilla_hello/consumer" "$cons" "received 'hello-nuropb-rmq'"
  pass_suite "vanilla_hello"
}

# --- vanilla_topic ---
smoke_topic() {
  local log peer_out
  log="$(mktemp)"
  python examples/vanilla_topic/subscriber.py >"$log" 2>&1 &
  local pid=$!
  sleep 0.8
  peer_out="$(python examples/vanilla_topic/publisher.py 2>&1)"
  sleep 0.5
  kill_bg "$pid"
  local sub
  sub="$(cat "$log")"
  rm -f "$log"
  assert_contains "vanilla_topic/publisher" "$peer_out" "logs.info"
  assert_contains "vanilla_topic/publisher" "$peer_out" "logs.error"
  assert_contains "vanilla_topic/publisher" "$peer_out" "logs.debug"
  assert_contains "vanilla_topic/subscriber" "$sub" "logs.info"
  assert_contains "vanilla_topic/subscriber" "$sub" "logs.error"
  assert_contains "vanilla_topic/subscriber" "$sub" "logs.debug"
  pass_suite "vanilla_topic"
}

# --- one_client_one_service ---
smoke_mesh() {
  local slog clout
  slog="$(mktemp)"
  python examples/one_client_one_service/service.py >"$slog" 2>&1 &
  local pid=$!
  sleep 1.5
  clout="$(python examples/one_client_one_service/client.py 2>&1)" || {
    kill_bg "$pid"
    echo "FAIL one_client_one_service/client exited non-zero" >&2
    echo "$clout" >&2
    cat "$slog" >&2
    rm -f "$slog"
    return 1
  }
  sleep 0.3
  kill_bg "$pid"
  rm -f "$slog"
  assert_contains "one_client_one_service/client" "$clout" "discovered"
  assert_contains "one_client_one_service/client" "$clout" "RPC demo.ping"
  assert_contains "one_client_one_service/client" "$clout" "RPC demo.echo"
  assert_contains "one_client_one_service/client" "$clout" "event demo.request_handled"
  pass_suite "one_client_one_service"
}

smoke_hello
smoke_topic
smoke_mesh
echo "All example smokes passed."
