#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean vs Python IO remasure (not an SLO). Needs a live broker + lake + uv.
#
# Local Homebrew defaults (RabbitMQ 4 loopback):
#   PLAIN  127.0.0.1:5673
#   AMQPS  127.0.0.1:5674   (Docker often owns :5671)
#
# Cells: raw firehose (dual-connection), rpc_classic, rpc_mesh_classic,
# rpc_mesh_quorum (serial + overlap).
#
# Inherited NUROPB_RMQ_PORT / NUROPB_RMQ_TLS are ignored so leftover Docker
# AMQPS env cannot poison the PLAIN cells.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${NUROPB_RMQ_HOST:-127.0.0.1}"
PLAIN_PORT="${NUROPB_REMEASURE_PLAIN_PORT:-5673}"
AMQPS_PORT="${NUROPB_REMEASURE_AMQPS_PORT:-5674}"
PASSES="${NUROPB_REMEASURE_PASSES:-2}"
DO_PLAIN=1
DO_AMQPS=1
DO_RAW=0
DO_RPC=0
DO_MESH=0
CELLS_SET=0
SKIP_BUILD=0
CA_FILE="${NUROPB_RMQ_CA_FILE:-$ROOT/dev/amqps/ca.pem}"
CERT_FILE="${NUROPB_RMQ_CERT_FILE:-$ROOT/dev/amqps/client.pem}"
KEY_FILE="${NUROPB_RMQ_KEY_FILE:-$ROOT/dev/amqps/client.key}"
SNI="${NUROPB_RMQ_SERVER_HOSTNAME:-localhost}"

usage() {
  cat <<'EOF'
Lean vs Python IO remasure (not an SLO). Needs a live broker + lake + uv.

Local Homebrew defaults: PLAIN 127.0.0.1:5673, AMQPS 127.0.0.1:5674

  ./scripts/remeasure_lean_python.sh
  ./scripts/remeasure_lean_python.sh --plain --raw
  ./scripts/remeasure_lean_python.sh --plain --rpc --mesh
  ./scripts/remeasure_lean_python.sh --amqps --mesh
  ./scripts/remeasure_lean_python.sh --plain-port 5672 --amqps-port 5671
  ./scripts/remeasure_lean_python.sh --passes 1 --skip-build

--raw / --rpc / --mesh select cells (default: all).
--plain / --amqps select transport (default: both).
Inherited NUROPB_RMQ_PORT / NUROPB_RMQ_TLS are ignored.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plain) DO_AMQPS=0 ;;
    --amqps) DO_PLAIN=0 ;;
    --both) DO_PLAIN=1; DO_AMQPS=1 ;;
    --raw) DO_RAW=1; CELLS_SET=1 ;;
    --rpc) DO_RPC=1; CELLS_SET=1 ;;
    --mesh) DO_MESH=1; CELLS_SET=1 ;;
    --plain-port) PLAIN_PORT="$2"; shift ;;
    --amqps-port) AMQPS_PORT="$2"; shift ;;
    --host) HOST="$2"; shift ;;
    --passes) PASSES="$2"; shift ;;
    --skip-build) SKIP_BUILD=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$CELLS_SET" -eq 0 ]]; then
  DO_RAW=1
  DO_RPC=1
  DO_MESH=1
fi

if [[ "$DO_PLAIN" -eq 0 && "$DO_AMQPS" -eq 0 ]]; then
  echo "nothing to run (pass --plain, --amqps, or --both)" >&2
  exit 2
fi
if [[ "$DO_RAW" -eq 0 && "$DO_RPC" -eq 0 && "$DO_MESH" -eq 0 ]]; then
  echo "nothing to run (pass --raw, --rpc, --mesh, or omit for all)" >&2
  exit 2
fi

CELLS=""
[[ "$DO_RAW" -eq 1 ]] && CELLS="${CELLS:+$CELLS,}raw"
[[ "$DO_RPC" -eq 1 ]] && CELLS="${CELLS:+$CELLS,}rpc"
[[ "$DO_MESH" -eq 1 ]] && CELLS="${CELLS:+$CELLS,}mesh"

probe() {
  local port="$1"
  python3 - "$HOST" "$port" <<'PY'
import socket, sys
host, port = sys.argv[1], int(sys.argv[2])
with socket.create_connection((host, port), 2):
    pass
PY
}

LEAN="$ROOT/.lake/build/bin/lean_bench_live"

if [[ "$SKIP_BUILD" -eq 0 ]]; then
  echo "===== lake build lean_bench_live ====="
  lake build lean_bench_live
fi
if [[ ! -x "$LEAN" ]]; then
  echo "missing $LEAN (run without --skip-build)" >&2
  exit 1
fi

run_python() {
  local kind="$1"
  NUROPB_BENCH_CELLS="$CELLS" uv run python -m bench.remeasure_io --kind "$kind" --cells "$CELLS"
}

run_lean_cell() {
  local mode="$1" count="$2" size="$3" queue="$4"
  NUROPB_BENCH_MODE="$mode" \
    NUROPB_BENCH_COUNT="$count" \
    NUROPB_BENCH_SIZE="$size" \
    NUROPB_BENCH_QUEUE="$queue" \
    "$LEAN"
}

run_lean_raw() {
  local tag="$1" serial="$2"
  if [[ "$serial" -eq 1 ]]; then
    run_lean_cell raw_serial 2000 64 "nr.bench.lean.${tag}.64"
    run_lean_cell raw_serial 2000 1024 "nr.bench.lean.${tag}.1k"
    run_lean_cell raw_serial 1000 16384 "nr.bench.lean.${tag}.16k"
  else
    run_lean_cell raw 2000 64 "nr.bench.lean.${tag}.64"
    run_lean_cell raw 2000 1024 "nr.bench.lean.${tag}.1k"
    run_lean_cell raw 1000 16384 "nr.bench.lean.${tag}.16k"
  fi
}

run_lean_rpc() {
  local tag="$1"
  run_lean_cell rpc_classic 200 64 "nr.bench.lean.${tag}.rpc"
  run_lean_cell rpc_classic_overlap 400 64 "nr.bench.lean.${tag}.ov"
}

run_lean_mesh() {
  local tag="$1"
  run_lean_cell rpc_mesh_classic 200 64 "nr.bench.lean.${tag}.mc"
  run_lean_cell rpc_mesh_classic_overlap 400 64 "nr.bench.lean.${tag}.mco"
  run_lean_cell rpc_mesh_quorum 200 64 "nr.bench.lean.${tag}.mq"
  run_lean_cell rpc_mesh_quorum_overlap 400 64 "nr.bench.lean.${tag}.mqo"
}

run_lean_pass() {
  local tag="$1" serial="$2"
  if [[ "$DO_RAW" -eq 1 ]]; then run_lean_raw "$tag" "$serial"; fi
  if [[ "$DO_RPC" -eq 1 ]]; then run_lean_rpc "$tag"; fi
  if [[ "$DO_MESH" -eq 1 ]]; then run_lean_mesh "$tag"; fi
}

export NUROPB_RMQ_HOST="$HOST"

if [[ "$DO_PLAIN" -eq 1 ]]; then
  if ! probe "$PLAIN_PORT"; then
    echo "PLAIN broker not reachable at ${HOST}:${PLAIN_PORT}" >&2
    exit 1
  fi
  unset NUROPB_RMQ_TLS NUROPB_RMQ_CA_FILE NUROPB_RMQ_CERT_FILE NUROPB_RMQ_KEY_FILE \
    NUROPB_RMQ_PKCS12_FILE NUROPB_RMQ_PKCS12_PASSWORD NUROPB_RMQ_SERVER_HOSTNAME \
    NUROPB_RMQ_AMQPS_PORT || true
  export NUROPB_RMQ_PORT="$PLAIN_PORT"
  for i in $(seq 1 "$PASSES"); do
    echo "===== PYTHON PLAIN pass ${i}/${PASSES} cells=${CELLS} (${HOST}:${PLAIN_PORT}) ====="
    run_python plain
    echo "===== LEAN PLAIN pass ${i}/${PASSES} cells=${CELLS} (${HOST}:${PLAIN_PORT}) ====="
    run_lean_pass "p${i}" 0
  done
fi

if [[ "$DO_AMQPS" -eq 1 ]]; then
  if [[ ! -f "$CA_FILE" || ! -f "$CERT_FILE" || ! -f "$KEY_FILE" ]]; then
    echo "AMQPS certs missing; run ./scripts/gen_amqps_certs.sh" >&2
    exit 1
  fi
  if ! probe "$AMQPS_PORT"; then
    echo "AMQPS broker not reachable at ${HOST}:${AMQPS_PORT}" >&2
    exit 1
  fi
  export NUROPB_RMQ_PORT="$AMQPS_PORT"
  export NUROPB_RMQ_TLS=1
  export NUROPB_RMQ_CA_FILE="$CA_FILE"
  export NUROPB_RMQ_CERT_FILE="$CERT_FILE"
  export NUROPB_RMQ_KEY_FILE="$KEY_FILE"
  export NUROPB_RMQ_SERVER_HOSTNAME="$SNI"
  for i in $(seq 1 "$PASSES"); do
    echo "===== PYTHON AMQPS pass ${i}/${PASSES} cells=${CELLS} (${HOST}:${AMQPS_PORT}) ====="
    run_python amqps
    echo "===== LEAN AMQPS pass ${i}/${PASSES} cells=${CELLS} (${HOST}:${AMQPS_PORT}) ====="
    run_lean_pass "t${i}" 1
  done
fi

echo "===== remasure done (not an SLO) ====="
