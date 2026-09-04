#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean mTLS + SASL EXTERNAL smoke. Reuses gen_amqps_certs.sh + mTLS broker conf.
# Not default lake build (needs OpenSSL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f dev/amqps/ca.pem || ! -f dev/amqps/client.pem || ! -f dev/amqps/client.key ]]; then
  ./scripts/gen_amqps_certs.sh
fi

mtls_tls_ok() {
  python3 - <<'PY' >/dev/null 2>&1
import ssl, socket
ctx = ssl.create_default_context(cafile="dev/amqps/ca.pem")
ctx.load_cert_chain("dev/amqps/client.pem", "dev/amqps/client.key")
with socket.create_connection(("127.0.0.1", 5671), 2) as raw:
    ctx.wrap_socket(raw, server_hostname="localhost")
PY
}

# PLAIN-over-TLS (rmq-amqps, verify_none) also accepts a client cert. Require
# the mTLS container so SASL EXTERNAL is actually offered.
if docker ps --format '{{.Names}}' | grep -qx rmq-amqps-mtls && mtls_tls_ok; then
  echo "reusing rmq-amqps-mtls"
else
  if docker ps -a --format '{{.Names}}' | grep -qx rmq-amqps; then
    docker rm -f rmq-amqps >/dev/null
  fi
  ./scripts/ci_start_amqps_mtls_broker.sh
fi

lake build NuropbRMQTls lean_amqps_mtls

export NUROPB_RMQ_TLS=1
export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
export NUROPB_RMQ_PORT="${NUROPB_RMQ_PORT:-5671}"
export NUROPB_RMQ_CA_FILE="${NUROPB_RMQ_CA_FILE:-$ROOT/dev/amqps/ca.pem}"
export NUROPB_RMQ_CERT_FILE="${NUROPB_RMQ_CERT_FILE:-$ROOT/dev/amqps/client.pem}"
export NUROPB_RMQ_KEY_FILE="${NUROPB_RMQ_KEY_FILE:-$ROOT/dev/amqps/client.key}"
export NUROPB_RMQ_SERVER_HOSTNAME="${NUROPB_RMQ_SERVER_HOSTNAME:-localhost}"

out="$("$ROOT/.lake/build/bin/lean_amqps_mtls")"
echo "$out"
if [[ "$out" != *"amqps-mtls: ok"* ]]; then
  echo "FAIL lean_amqps_mtls" >&2
  exit 1
fi
echo "PASS lean_amqps_mtls"
