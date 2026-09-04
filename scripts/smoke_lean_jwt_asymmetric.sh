#!/usr/bin/env bash
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

# Lean OpenSSL RS256/ES256 JWT verify against PyJWT goldens. No broker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

lake build lean_jwt_asymmetric
out="$("$ROOT/.lake/build/bin/lean_jwt_asymmetric")"
echo "$out"
if [[ "$out" != *"jwt-asym: ok"* ]]; then
  echo "FAIL lean_jwt_asymmetric" >&2
  exit 1
fi
echo "PASS lean_jwt_asymmetric"
