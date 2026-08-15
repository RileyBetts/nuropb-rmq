#!/usr/bin/env python3
# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""SpeC++ CheckSat gate for Protocol + Session + Pattern + Config clauses.

Runs Z3 against SMT-LIB specs under specs/specpp/.
Exit 0 only if every expected-sat file is sat and every expected-unsat
file is unsat. UNKNOWN is a hard failure (no waiver).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# (subdir, filename, expected result)
CHECKS: list[tuple[str, str, str]] = [
    ("Protocol", "connection_channel_sm.smt2", "sat"),
    ("Protocol", "connection_channel_sm_negatives.smt2", "unsat"),
    ("Protocol", "frame_bounds.smt2", "sat"),
    ("Protocol", "frame_bounds_negatives.smt2", "unsat"),
    ("Protocol", "publisher_confirms.smt2", "sat"),
    ("Protocol", "publisher_confirms_negatives.smt2", "unsat"),
    ("Protocol", "connection_blocked.smt2", "sat"),
    ("Protocol", "connection_blocked_negatives.smt2", "unsat"),
    ("Protocol", "basic_return.smt2", "sat"),
    ("Protocol", "basic_return_negatives.smt2", "unsat"),
    ("Session", "correlation.smt2", "sat"),
    ("Session", "correlation_negatives.smt2", "unsat"),
    ("Session", "phase2_reconnect.smt2", "sat"),
    ("Session", "phase2_reconnect_negatives.smt2", "unsat"),
    ("Pattern", "mesh_claims.smt2", "sat"),
    ("Pattern", "mesh_claims_negatives.smt2", "unsat"),
    ("Config", "queue_profile.smt2", "sat"),
    ("Config", "queue_profile_negatives.smt2", "unsat"),
]


def run_z3(path: Path) -> str:
    proc = subprocess.run(
        ["z3", "-smt2", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").strip().splitlines()
    if not out:
        raise RuntimeError(f"z3 produced no output for {path}: {proc.stderr}")
    # Last non-empty line that is sat/unsat/unknown (ignore get-model noise)
    for line in reversed(out):
        token = line.strip().lower()
        if token in {"sat", "unsat", "unknown"}:
            return token
    return out[-1].strip()


def main() -> int:
    failures: list[str] = []
    for sub, name, expected in CHECKS:
        path = ROOT / sub / name
        rel = f"{sub}/{name}"
        if not path.exists():
            failures.append(f"missing {path}")
            continue
        result = run_z3(path)
        print(f"{rel}: {result} (expected {expected})")
        if result == "unknown":
            failures.append(f"{rel}: UNKNOWN (no waiver)")
        elif result != expected:
            failures.append(f"{rel}: got {result}, expected {expected}")
    if failures:
        print("CheckSat FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("CheckSat PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
