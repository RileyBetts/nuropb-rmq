#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Two-phase Docker RabbitMQ (same run shape as ci_start_amqps_broker.sh:
# default entrypoint, no --hostname, no cookie env).
#
# 1. Boot the *PLAIN* AMQPS conf. verify_peer / EXTERNAL in the first
#    rabbitmq.conf makes prelaunch fail on GitHub Actions with
#    .erlang.cookie eacces (the AMQPS job uses this exact file and is green).
# 2. After ping: enable rabbitmq_auth_mechanism_ssl, add CN user, permissions.
# 3. Recreate with the full mTLS conf + the persisted enabled_plugins so
#    EXTERNAL is legal at prelaunch.
# Maps CN nuropb-client.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLIENT_CN="${NUROPB_AMQPS_CLIENT_CN:-nuropb-client}"
PLUGINS_RUNTIME="$ROOT/scripts/.rabbitmq-mtls.enabled_plugins"

chmod a+r dev/amqps/ca.pem dev/amqps/server.pem dev/amqps/server.key \
  dev/amqps/client.pem

if docker ps -a --format '{{.Names}}' | grep -qx rmq-amqps-mtls; then
  docker rm -fv rmq-amqps-mtls >/dev/null
fi

docker run -d --name rmq-amqps-mtls \
  -p 5671:5671 \
  -v "$PWD/dev/amqps:/certs:ro" \
  -v "$PWD/scripts/rabbitmq-amqps.ci.conf:/etc/rabbitmq/rabbitmq.conf:ro" \
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

wait_broker() {
  local label="$1"
  for _ in $(seq 1 60); do
    if broker_ready; then
      echo "$label"
      return 0
    fi
    sleep 2
  done
  docker logs rmq-amqps-mtls || true
  echo "RabbitMQ did not become ready ($label)" >&2
  return 1
}

wait_broker "AMQPS mTLS phase 1 ready (PLAIN AMQPS conf)"

docker exec rmq-amqps-mtls rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
docker exec rmq-amqps-mtls rabbitmqctl add_user "$CLIENT_CN" unused-password || true
docker exec rmq-amqps-mtls rabbitmqctl set_permissions -p / "$CLIENT_CN" ".*" ".*" ".*"
docker cp rmq-amqps-mtls:/etc/rabbitmq/enabled_plugins "$PLUGINS_RUNTIME"
chmod 644 "$PLUGINS_RUNTIME"

docker rm -fv rmq-amqps-mtls >/dev/null

docker run -d --name rmq-amqps-mtls \
  -p 5671:5671 \
  -v "$PWD/dev/amqps:/certs:ro" \
  -v "$PWD/scripts/rabbitmq-amqps-mtls.ci.conf:/etc/rabbitmq/rabbitmq.conf:ro" \
  -v "$PLUGINS_RUNTIME:/etc/rabbitmq/enabled_plugins" \
  rabbitmq:3-management

wait_broker "AMQPS mTLS phase 2 ready (EXTERNAL in conf + plugin)"

for _ in $(seq 1 60); do
  if mtls_ready; then
    echo "AMQPS mTLS listener ready (EXTERNAL, CN=${CLIENT_CN})"
    exit 0
  fi
  sleep 2
done

docker logs rmq-amqps-mtls || true
exit 1
