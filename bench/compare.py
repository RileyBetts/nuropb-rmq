# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""CLI: run throughput matrix comparing nuropb-rmq vs pika.

Usage:
  pip install -e ".[bench]"
  python -m bench.compare
  NUROPB_BENCH_COUNT=200 python -m bench.compare --quick
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bench.common import (
    BenchResult,
    broker_host,
    broker_port,
    concurrencies,
    message_count_default,
    payload_sizes,
)


def _require_pika() -> None:
    try:
        import pika  # noqa: F401
    except ImportError:
        print(
            "pika is required for the bench harness. Install with:\n"
            '  pip install -e ".[bench]"',
            file=sys.stderr,
        )
        raise SystemExit(2)


def _md_table(rows: list[BenchResult]) -> str:
    lines = [
        "| library | scenario | bytes | conc | count | msgs/s | p50 ms | p99 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        p50 = f"{r.latency_p50_ms:.2f}" if r.latency_p50_ms is not None else "-"
        p99 = f"{r.latency_p99_ms:.2f}" if r.latency_p99_ms is not None else "-"
        lines.append(
            f"| {r.library} | {r.scenario} | {r.payload_bytes} | {r.concurrency} | "
            f"{r.message_count} | {r.msgs_per_sec:.0f} | {p50} | {p99} |"
        )
    return "\n".join(lines)


async def _run_nuropb_cell(
    scenario: str,
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
    subscribers: int,
) -> BenchResult:
    if scenario == "raw_publish_consume":
        from bench.runners.nuropb_raw import run_raw_publish_consume

        return await run_raw_publish_consume(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
        )
    if scenario == "rpc_exclusive_reply":
        from bench.runners.nuropb_rpc import run_rpc_exclusive

        return await run_rpc_exclusive(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
        )
    if scenario == "event_fanout":
        from bench.runners.nuropb_fanout import run_event_fanout

        return await run_event_fanout(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
            subscribers=subscribers,
        )
    raise ValueError(f"unknown nuropb scenario {scenario}")


def _run_pika_cell(
    scenario: str,
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
    subscribers: int,
) -> BenchResult:
    from bench.runners import pika_runners as pk

    if scenario == "raw_publish_consume":
        return pk.run_raw_publish_consume(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
        )
    if scenario == "rpc_exclusive_reply":
        return pk.run_rpc_exclusive(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
        )
    if scenario == "rpc_direct_reply_to":
        return pk.run_rpc_direct_reply_to(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
        )
    if scenario == "event_fanout":
        return pk.run_event_fanout(
            payload_bytes=payload_bytes,
            concurrency=concurrency,
            message_count=message_count,
            subscribers=subscribers,
        )
    raise ValueError(f"unknown pika scenario {scenario}")


async def run_matrix(
    *,
    message_count: int,
    sizes: list[int],
    concs: list[int],
    fanout_subscribers: list[int],
    scenarios: list[str],
) -> list[BenchResult]:
    results: list[BenchResult] = []
    for size in sizes:
        for conc in concs:
            for scenario in scenarios:
                if scenario == "rpc_direct_reply_to":
                    print(f"pika {scenario} size={size} conc={conc} ...", flush=True)
                    results.append(
                        _run_pika_cell(
                            scenario,
                            payload_bytes=size,
                            concurrency=conc,
                            message_count=message_count,
                            subscribers=1,
                        )
                    )
                    continue
                if scenario == "event_fanout":
                    for nsub in fanout_subscribers:
                        print(
                            f"nuropb-rmq {scenario} size={size} conc={conc} subs={nsub} ...",
                            flush=True,
                        )
                        results.append(
                            await _run_nuropb_cell(
                                scenario,
                                payload_bytes=size,
                                concurrency=conc,
                                message_count=message_count,
                                subscribers=nsub,
                            )
                        )
                        print(
                            f"pika {scenario} size={size} conc={conc} subs={nsub} ...",
                            flush=True,
                        )
                        results.append(
                            _run_pika_cell(
                                scenario,
                                payload_bytes=size,
                                concurrency=conc,
                                message_count=message_count,
                                subscribers=nsub,
                            )
                        )
                    continue
                print(f"nuropb-rmq {scenario} size={size} conc={conc} ...", flush=True)
                results.append(
                    await _run_nuropb_cell(
                        scenario,
                        payload_bytes=size,
                        concurrency=conc,
                        message_count=message_count,
                        subscribers=1,
                    )
                )
                print(f"pika {scenario} size={size} conc={conc} ...", flush=True)
                results.append(
                    _run_pika_cell(
                        scenario,
                        payload_bytes=size,
                        concurrency=conc,
                        message_count=message_count,
                        subscribers=1,
                    )
                )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="nuropb-rmq vs pika throughput compare")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="small matrix (count from env or 200; sizes 64; conc 1)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="messages per cell (default NUROPB_BENCH_COUNT or 10000)",
    )
    parser.add_argument(
        "--scenarios",
        default="raw_publish_consume,rpc_exclusive_reply,rpc_direct_reply_to,event_fanout",
        help="comma-separated scenario names",
    )
    args = parser.parse_args(argv)
    _require_pika()

    # Probe broker early
    host, port = broker_host(), broker_port()
    print(f"broker {host}:{port}", flush=True)

    if args.quick:
        count = args.count or int(__import__("os").environ.get("NUROPB_BENCH_COUNT", "200"))
        sizes = [64]
        concs = [1]
        fanout_subs = [1]
    else:
        count = args.count or message_count_default()
        sizes = payload_sizes()
        concs = concurrencies()
        fanout_subs = [1, 3]

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]
    results = asyncio.run(
        run_matrix(
            message_count=count,
            sizes=sizes,
            concs=concs,
            fanout_subscribers=fanout_subs,
            scenarios=scenarios,
        )
    )

    out_dir = Path(__file__).resolve().parent / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{stamp}.json"
    payload = {
        "broker": {"host": host, "port": port},
        "generated_at": stamp,
        "results": [r.to_dict() for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print()
    print(_md_table(results))
    print()
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
