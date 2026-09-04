#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Start Docker RabbitMQ with verify_peer + SASL EXTERNAL and wait until mTLS works.
# Maps client cert CN (nuropb-client) via rabbitmq_auth_mechanism_ssl.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLIENT_CN="${NUROPB_AMQPS_CLIENT_CN:-nuropb-client}"

chmod a+r dev/amqps/ca.pem dev/amqps/server.pem dev/amqps/server.key \
  dev/amqps/client.pem

if docker ps -a --format '{{.Names}}' | grep -qx rmq-amqps-mtls; then
  docker rm -f rmq-amqps-mtls >/dev/null
fi

# Same shape as ci_start_amqps_broker.sh. Do not override entrypoint or
# --hostname (both break the image cookie / prelaunch on Docker Desktop).
docker run -d --name rmq-amqps-mtls \
  -p 5671:5671 \
  -v "$PWD/dev/amqps:/certs:ro" \
  -v "$PWD/scripts/rabbitmq-amqps-mtls.ci.conf:/etc/rabbitmq/rabbitmq.conf:ro" \
  rabbitmq:3-management

mtls_ready() {
  python3 - <<'PY'
import ssl
import socket
import sys

ctx = ssl.create_default_context(cafile="dev/amqps/ca.pem")
ctx.load_cert_chain("dev/amqps/client.pem", "dev/amqps/client.key")
try:
    with socket.create_connection(("127.0.0.1", 5671), 2) as raw:
        ctx.wrap_socket(raw, server_hostname="localhost")
except Exception as exc:
    print(exc)
    sys.exit(1)
PY
}

broker_ready() {
  docker exec rmq-amqps-mtls rabbitmq-diagnostics -q ping >/dev/null 2>&1
}

for _ in $(seq 1 60); do
  if broker_ready; then
    break
  fi
  sleep 2
done

if ! broker_ready; then
  docker logs rmq-amqps-mtls || true
  echo "RabbitMQ did not become ready" >&2
  exit 1
fi

docker exec rmq-amqps-mtls rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
docker exec rmq-amqps-mtls rabbitmqctl add_user "$CLIENT_CN" unused-password || true
docker exec rmq-amqps-mtls rabbitmqctl set_permissions -p / "$CLIENT_CN" ".*" ".*" ".*"

for _ in $(seq 1 60); do
  if mtls_ready; then
    echo "AMQPS mTLS listener ready (EXTERNAL, CN=${CLIENT_CN})"
    exit 0
  fi
  sleep 2
done

docker logs rmq-amqps-mtls || true
exit 1
