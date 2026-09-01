#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Start Docker RabbitMQ with the CI AMQPS conf and wait until TLS works.
# Docker's published-port proxy accepts TCP before the SSL listener exists.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Broker uid in the image must read host-mounted key material.
chmod a+r dev/amqps/ca.pem dev/amqps/server.pem dev/amqps/server.key

docker run -d --name rmq-amqps \
  -p 5671:5671 \
  -v "$PWD/dev/amqps:/certs:ro" \
  -v "$PWD/scripts/rabbitmq-amqps.ci.conf:/etc/rabbitmq/rabbitmq.conf:ro" \
  rabbitmq:3-management

tls_ready() {
  python3 - <<'PY'
import ssl
import socket
import sys

ctx = ssl.create_default_context(cafile="dev/amqps/ca.pem")
try:
    with socket.create_connection(("127.0.0.1", 5671), 2) as raw:
        ctx.wrap_socket(raw, server_hostname="localhost")
except Exception as exc:
    print(exc)
    sys.exit(1)
PY
}

for _ in $(seq 1 60); do
  if tls_ready; then
    echo "AMQPS listener ready"
    exit 0
  fi
  sleep 2
done

docker logs rmq-amqps || true
exit 1
