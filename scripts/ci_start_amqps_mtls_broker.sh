#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# 1. Start with the green AMQPS starter (same docker run as `amqps` /
#    `lean-amqps`: name rmq-amqps, PLAIN conf). Do not first-boot
#    verify_peer or EXTERNAL — that fails prelaunch on GitHub Actions
#    (.erlang.cookie eacces). Do not recreate the container.
# 2. Rename, enable rabbitmq_auth_mechanism_ssl, add CN user.
# 3. Drop verify_peer + EXTERNAL into conf.d (writable in-image) and
#    restart the same container so the cookie and enabled_plugins stay.
# Maps CN nuropb-client.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CLIENT_CN="${NUROPB_AMQPS_CLIENT_CN:-nuropb-client}"

for name in rmq-amqps-mtls rmq-amqps; do
  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    docker rm -fv "$name" >/dev/null
  fi
done

"$ROOT/scripts/ci_start_amqps_broker.sh"
docker rename rmq-amqps rmq-amqps-mtls

docker exec rmq-amqps-mtls rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
docker exec rmq-amqps-mtls rabbitmqctl add_user "$CLIENT_CN" unused-password || true
docker exec rmq-amqps-mtls rabbitmqctl set_permissions -p / "$CLIENT_CN" ".*" ".*" ".*"

docker exec rmq-amqps-mtls sh -c 'cat > /etc/rabbitmq/conf.d/99-mtls-external.conf <<EOF
ssl_options.verify = verify_peer
ssl_options.fail_if_no_peer_cert = true
ssl_cert_login_from = common_name
auth_mechanisms.1 = PLAIN
auth_mechanisms.2 = AMQPLAIN
auth_mechanisms.3 = EXTERNAL
EOF'

docker restart rmq-amqps-mtls >/dev/null

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
    echo "AMQPS mTLS phase 2 ready (same node + conf.d EXTERNAL)"
    break
  fi
  sleep 2
done

if ! broker_ready; then
  docker logs rmq-amqps-mtls || true
  echo "RabbitMQ did not become ready after conf.d EXTERNAL" >&2
  exit 1
fi

for _ in $(seq 1 60); do
  if mtls_ready; then
    echo "AMQPS mTLS listener ready (EXTERNAL, CN=${CLIENT_CN})"
    exit 0
  fi
  sleep 2
done

docker logs rmq-amqps-mtls || true
exit 1
