# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Guards and small-count smoke for the throughput harness."""

from __future__ import annotations

import ast
import os
import socket
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"


def test_src_never_imports_pika() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "pika" or alias.name.startswith("pika."):
                        offenders.append(str(path.relative_to(ROOT)))
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "pika" or mod.startswith("pika."):
                    offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"pika imported from src/: {offenders}"


def _broker_available() -> bool:
    host = os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")
    if "NUROPB_RMQ_PORT" in os.environ:
        ports = [int(os.environ["NUROPB_RMQ_PORT"])]
    else:
        ports = [5672, 5673]
    for port in ports:
        with socket.socket() as s:
            s.settimeout(0.2)
            try:
                s.connect((host, port))
                return True
            except OSError:
                continue
    return False


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_bench_smoke_nuropb_raw() -> None:
    if not _broker_available():
        pytest.skip("RabbitMQ not available")
    from bench.runners.nuropb_raw import run_raw_publish_consume

    result = await run_raw_publish_consume(payload_bytes=64, concurrency=1, message_count=50)
    assert result.message_count == 50
    assert result.msgs_per_sec > 0


@pytest.mark.benchmark
def test_bench_smoke_pika_raw() -> None:
    if not _broker_available():
        pytest.skip("RabbitMQ not available")
    pytest.importorskip("pika")
    from bench.runners.pika_runners import run_raw_publish_consume

    result = run_raw_publish_consume(payload_bytes=64, concurrency=1, message_count=50)
    assert result.message_count == 50
    assert result.msgs_per_sec > 0


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_bench_smoke_nuropb_rpc_and_fanout() -> None:
    if not _broker_available():
        pytest.skip("RabbitMQ not available")
    from bench.runners.nuropb_fanout import run_event_fanout
    from bench.runners.nuropb_rpc import run_rpc_exclusive

    rpc = await run_rpc_exclusive(payload_bytes=64, concurrency=1, message_count=20)
    assert rpc.msgs_per_sec > 0
    fan = await run_event_fanout(
        payload_bytes=64, concurrency=1, message_count=20, subscribers=1
    )
    assert fan.msgs_per_sec > 0


@pytest.mark.benchmark
def test_bench_smoke_pika_direct_and_fanout() -> None:
    if not _broker_available():
        pytest.skip("RabbitMQ not available")
    pytest.importorskip("pika")
    from bench.runners.pika_runners import run_event_fanout, run_rpc_direct_reply_to

    direct = run_rpc_direct_reply_to(payload_bytes=64, concurrency=1, message_count=20)
    assert direct.msgs_per_sec > 0
    fan = run_event_fanout(payload_bytes=64, concurrency=1, message_count=20, subscribers=1)
    assert fan.msgs_per_sec > 0
