#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean live reply-forge 403 with narrower-than-prefix regex broker perms.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
export NUROPB_RMQ_PORT="${NUROPB_RMQ_PORT:-5672}"
export NUROPB_RMQ_MGMT_PORT="${NUROPB_RMQ_MGMT_PORT:-15672}"
export NUROPB_RMQ_USER=guest
export NUROPB_RMQ_PASSWORD=guest
unset NUROPB_RMQ_TLS NUROPB_RMQ_CERT_FILE NUROPB_RMQ_KEY_FILE \
  NUROPB_RMQ_PKCS12_FILE NUROPB_RMQ_PKCS12_PASSWORD NUROPB_RMQ_CA_FILE

if ! python3 - <<'PY' >/dev/null 2>&1
import os, socket
s = socket.create_connection((os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"), int(os.environ.get("NUROPB_RMQ_MGMT_PORT", "15672"))), 1)
s.close()
PY
then
  echo "RabbitMQ management API not listening on ${NUROPB_RMQ_MGMT_PORT}" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/setup_reply_acl_regex_users.sh"

lake build lean_reply_acl
out="$("$ROOT/.lake/build/bin/lean_reply_acl")"
echo "$out"
if [[ "$out" != *"reply-acl: forge denied 403"* || "$out" != *"reply-acl: service publish ok"* ]]; then
  echo "FAIL lean_reply_acl_regex" >&2
  exit 1
fi
echo "PASS lean_reply_acl_regex"
