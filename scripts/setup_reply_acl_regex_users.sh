#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Narrower-than-prefix regex ACL users for the Lean reply-forge 403 smoke.
set -euo pipefail

HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
MGMT_PORT="${NUROPB_RMQ_MGMT_PORT:-15672}"
ADMIN_USER="${NUROPB_RMQ_USER:-guest}"
ADMIN_PASS="${NUROPB_RMQ_PASSWORD:-guest}"
PW="${NUROPB_RMQ_ACL_PASSWORD:-acl-test-secret}"

suffix="$(python3 -c 'import uuid; print(uuid.uuid4().hex[:8])')"
CLIENT="nr.acl.re.client.${suffix}"
SVC="nr.acl.re.svc.${suffix}"
VICTIM="nr.reply.${suffix}victim"

mgmt() {
  local method="$1" path="$2" body="$3"
  curl -sS -f -u "${ADMIN_USER}:${ADMIN_PASS}" -X "$method" \
    -H "Content-Type: application/json" \
    -d "$body" \
    "http://${HOST}:${MGMT_PORT}${path}" >/dev/null
}

mgmt PUT "/api/users/${CLIENT}" "{\"password\":\"${PW}\",\"tags\":\"\"}"
mgmt PUT "/api/users/${SVC}" "{\"password\":\"${PW}\",\"tags\":\"\"}"
mgmt PUT "/api/permissions/%2F/${CLIENT}" \
  '{"configure":"^nr\\.reply\\.[0-9a-f]{8}","write":"^nr\\.mesh$","read":"^nr\\.reply\\.[0-9a-f]{8}"}'
mgmt PUT "/api/permissions/%2F/${SVC}" \
  '{"configure":"^nr\\.reply\\.[0-9a-f]{8}","write":"^nr\\.reply\\.[0-9a-f]{8}|^nr\\.mesh$|^amq\\.default$","read":"^nr\\.reply\\.[0-9a-f]{8}"}'

export NUROPB_RMQ_ACL_CLIENT="$CLIENT"
export NUROPB_RMQ_ACL_SVC="$SVC"
export NUROPB_RMQ_ACL_PASSWORD="$PW"
export NUROPB_RMQ_ACL_VICTIM="$VICTIM"
echo "ACL regex users ${CLIENT} / ${SVC} victim ${VICTIM}"
