#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Two-phase Docker RabbitMQ (same run shape as ci_start_amqps_broker.sh:
# default entrypoint, no --hostname, no cookie env).
#
# 1. Boot verify_peer only — do not list EXTERNAL or ssl_cert_login_from.
#    Those make prelaunch fail with .erlang.cookie eacces before
#    rabbitmq_auth_mechanism_ssl is loaded.
# 2. After ping: enable the plugin, add CN user, permissions.
# 3. Swap in the full conf (EXTERNAL + common_name) and restart the same
#    container so enabled_plugins survives.
# Maps CN nuropb-client.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLIENT_CN="${NUROPB_AMQPS_CLIENT_CN:-nuropb-client}"

chmod a+r dev/amqps/ca.pem dev/amqps/server.pem dev/amqps/server.key \
  dev/amqps/client.pem

if docker ps -a --format '{{.Names}}' | grep -qx rmq-amqps-mtls; then
  docker rm -fv rmq-amqps-mtls >/dev/null
fi

# Host-writable copy so phase 3 can swap EXTERNAL in. Keep it next to
# the other CI confs (not under /certs — overlapping binds break boot).
CONF_RUNTIME="$ROOT/scripts/.rabbitmq-mtls.runtime.conf"
cp "$ROOT/scripts/rabbitmq-amqps-mtls-boot.ci.conf" "$CONF_RUNTIME"
chmod 644 "$CONF_RUNTIME"

docker run -d --name rmq-amqps-mtls \
  -p 5671:5671 \
  -v "$PWD/dev/amqps:/certs:ro" \
  -v "$CONF_RUNTIME:/etc/rabbitmq/rabbitmq.conf:ro" \
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

wait_broker "AMQPS mTLS phase 1 ready (verify_peer)"

docker exec rmq-amqps-mtls rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
docker exec rmq-amqps-mtls rabbitmqctl add_user "$CLIENT_CN" unused-password || true
docker exec rmq-amqps-mtls rabbitmqctl set_permissions -p / "$CLIENT_CN" ".*" ".*" ".*"

cp "$ROOT/scripts/rabbitmq-amqps-mtls.ci.conf" "$CONF_RUNTIME"
chmod 644 "$CONF_RUNTIME"
docker restart rmq-amqps-mtls >/dev/null

wait_broker "AMQPS mTLS phase 2 ready (EXTERNAL in conf)"

for _ in $(seq 1 60); do
  if mtls_ready; then
    echo "AMQPS mTLS listener ready (EXTERNAL, CN=${CLIENT_CN})"
    exit 0
  fi
  sleep 2
done

docker logs rmq-amqps-mtls || true
exit 1
