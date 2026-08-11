#!/usr/bin/env python3
"""SpeC++ CheckSat gate for Protocol SM clauses.

Runs Z3 against SMT-LIB specs under specs/specpp/Protocol/.
Exit 0 only if every expected-sat file is sat and every expected-unsat
file is unsat. UNKNOWN is a hard failure (no waiver).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROTOCOL = ROOT / "Protocol"

# (path relative to Protocol/, expected result)
CHECKS: list[tuple[str, str]] = [
    ("connection_channel_sm.smt2", "sat"),
    ("connection_channel_sm_negatives.smt2", "unsat"),
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
    # Last non-empty line is the check-sat result
    return out[-1].strip()


def main() -> int:
    failures: list[str] = []
    for rel, expected in CHECKS:
        path = PROTOCOL / rel
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
