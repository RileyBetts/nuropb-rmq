#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Generate a local CA + RabbitMQ server + client certs for AMQPS / mTLS smoke.
# Writes into dev/amqps/ (gitignored). Does not configure the broker.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${NUROPB_AMQPS_DIR:-$ROOT/dev/amqps}"
mkdir -p "$OUT"

DAYS="${NUROPB_AMQPS_DAYS:-825}"
SUBJ_SRV="/CN=localhost"
CLIENT_CN="${NUROPB_AMQPS_CLIENT_CN:-nuropb-client}"

openssl genrsa -out "$OUT/ca.key" 2048
cat >"$OUT/ca.cnf" <<EOF
[req]
distinguished_name = req_dn
x509_extensions = v3_ca
prompt = no

[req_dn]
CN = nuropb-rmq-dev-ca

[v3_ca]
basicConstraints = critical,CA:TRUE
keyUsage = critical,keyCertSign,cRLSign
subjectKeyIdentifier = hash
EOF
openssl req -x509 -new -nodes -key "$OUT/ca.key" -sha256 -days "$DAYS" \
  -config "$OUT/ca.cnf" -out "$OUT/ca.pem"

openssl genrsa -out "$OUT/server.key" 2048
openssl req -new -key "$OUT/server.key" -subj "$SUBJ_SRV" -out "$OUT/server.csr"

cat >"$OUT/server.ext" <<'EOF'
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=serverAuth
subjectAltName=DNS:localhost,IP:127.0.0.1
EOF

openssl x509 -req -in "$OUT/server.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
  -CAcreateserial -out "$OUT/server.pem" -days "$DAYS" -sha256 -extfile "$OUT/server.ext"

openssl genrsa -out "$OUT/client.key" 2048
openssl req -new -key "$OUT/client.key" -subj "/CN=${CLIENT_CN}" -out "$OUT/client.csr"

cat >"$OUT/client.ext" <<'EOF'
basicConstraints=CA:FALSE
keyUsage=digitalSignature,keyEncipherment
extendedKeyUsage=clientAuth
EOF

openssl x509 -req -in "$OUT/client.csr" -CA "$OUT/ca.pem" -CAkey "$OUT/ca.key" \
  -CAcreateserial -out "$OUT/client.pem" -days "$DAYS" -sha256 -extfile "$OUT/client.ext"

chmod 600 "$OUT/ca.key" "$OUT/server.key" "$OUT/client.key"
rm -f "$OUT/server.csr" "$OUT/server.ext" "$OUT/client.csr" "$OUT/client.ext" \
  "$OUT/ca.cnf" "$OUT/ca.srl"

cat <<EOF

Generated AMQPS trust material in:
  $OUT/ca.pem       (trust anchor)
  $OUT/server.pem   (broker certificate)
  $OUT/server.key   (broker private key)
  $OUT/client.pem   (client certificate, CN=${CLIENT_CN})
  $OUT/client.key   (client private key)

PLAIN over TLS (see scripts/rabbitmq-amqps.conf.example):

  export NUROPB_RMQ_TLS=1
  export NUROPB_RMQ_HOST=127.0.0.1
  export NUROPB_RMQ_PORT=5671
  export NUROPB_RMQ_CA_FILE=$OUT/ca.pem
  export NUROPB_RMQ_SERVER_HOSTNAME=localhost
  pytest -q tests/integration/test_amqps_smoke.py

mTLS + SASL EXTERNAL (see scripts/rabbitmq-amqps-mtls.conf.example):

  rabbitmq-plugins enable rabbitmq_auth_mechanism_ssl
  rabbitmqctl add_user ${CLIENT_CN} unused-password-ignored-by-external || true
  rabbitmqctl set_permissions -p / ${CLIENT_CN} ".*" ".*" ".*"
  # point broker at mTLS example conf, restart, then:

  export NUROPB_RMQ_MTLS=1
  export NUROPB_RMQ_HOST=127.0.0.1
  export NUROPB_RMQ_PORT=5671
  export NUROPB_RMQ_CA_FILE=$OUT/ca.pem
  export NUROPB_RMQ_CERT_FILE=$OUT/client.pem
  export NUROPB_RMQ_KEY_FILE=$OUT/client.key
  export NUROPB_RMQ_SERVER_HOSTNAME=localhost
  pytest -q tests/integration/test_amqps_mtls_smoke.py

EOF
