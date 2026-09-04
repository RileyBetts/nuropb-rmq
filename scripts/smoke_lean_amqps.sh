#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean tls-verify-full smoke. Reuses Python AMQPS certs + broker scripts.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f dev/amqps/ca.pem ]]; then
  ./scripts/gen_amqps_certs.sh
fi

if ! python3 - <<'PY' >/dev/null 2>&1
import ssl, socket
ctx = ssl.create_default_context(cafile="dev/amqps/ca.pem")
with socket.create_connection(("127.0.0.1", 5671), 2) as raw:
    ctx.wrap_socket(raw, server_hostname="localhost")
PY
then
  if docker ps -a --format '{{.Names}}' | grep -qx rmq-amqps; then
    docker rm -f rmq-amqps >/dev/null
  fi
  ./scripts/ci_start_amqps_broker.sh
fi

lake build NuropbRMQTls lean_amqps_hello

export NUROPB_RMQ_TLS=1
export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
# Do not inherit a PLAIN leftover (`NUROPB_RMQ_PORT=5672` → wrong version number).
export NUROPB_RMQ_PORT="${NUROPB_RMQ_AMQPS_PORT:-5671}"
export NUROPB_RMQ_CA_FILE="${NUROPB_RMQ_CA_FILE:-$ROOT/dev/amqps/ca.pem}"
export NUROPB_RMQ_SERVER_HOSTNAME="${NUROPB_RMQ_SERVER_HOSTNAME:-localhost}"
# mTLS broker on 5671 requires a client cert; PLAIN-over-TLS does not.
if docker ps --format '{{.Names}}' | grep -qx rmq-amqps-mtls; then
  export NUROPB_RMQ_CERT_FILE="${NUROPB_RMQ_CERT_FILE:-$ROOT/dev/amqps/client.pem}"
  export NUROPB_RMQ_KEY_FILE="${NUROPB_RMQ_KEY_FILE:-$ROOT/dev/amqps/client.key}"
fi

out="$("$ROOT/.lake/build/bin/lean_amqps_hello")"
echo "$out"
if [[ "$out" != *"amqps: ok"* ]]; then
  echo "FAIL lean_amqps_hello" >&2
  exit 1
fi
echo "PASS lean_amqps_hello"
