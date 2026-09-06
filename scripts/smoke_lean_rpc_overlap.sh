#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# One Lean session, eight in-flight stub RPCs. Needs RabbitMQ + lake.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export NUROPB_RMQ_HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
export NUROPB_RMQ_PORT="${NUROPB_RMQ_PORT:-5672}"
unset NUROPB_RMQ_TLS || true
lake build lean_rpc_overlap
out="$("$ROOT/.lake/build/bin/lean_rpc_overlap" 2>&1)"
if [[ "$out" != *"lean_rpc_overlap: ok"* ]]; then
  echo "FAIL lean_rpc_overlap: $out" >&2
  exit 1
fi
echo "PASS lean_rpc_overlap"
