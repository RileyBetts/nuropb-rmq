"""Shared broker discovery, payloads, and metrics for throughput benches."""

from __future__ import annotations

import math
import os
import socket
import time
from dataclasses import asdict, dataclass, field
from typing import Any


def broker_host() -> str:
    return os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1")


def broker_port() -> int:
    if "NUROPB_RMQ_PORT" in os.environ:
        return int(os.environ["NUROPB_RMQ_PORT"])
    for port in (5672, 5673):
        with socket.socket() as s:
            s.settimeout(0.2)
            try:
                s.connect((broker_host(), port))
                return port
            except OSError:
                continue
    raise RuntimeError("RabbitMQ not listening on 5672/5673 (set NUROPB_RMQ_HOST/PORT)")


def broker_url_amqp() -> str:
    user = os.environ.get("NUROPB_RMQ_USER", "guest")
    password = os.environ.get("NUROPB_RMQ_PASSWORD", "guest")
    return f"amqp://{user}:{password}@{broker_host()}:{broker_port()}/%2F"


def message_count_default() -> int:
    return int(os.environ.get("NUROPB_BENCH_COUNT", "10000"))


def payload_sizes() -> list[int]:
    raw = os.environ.get("NUROPB_BENCH_SIZES", "64,1024,16384")
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def concurrencies() -> list[int]:
    raw = os.environ.get("NUROPB_BENCH_CONCURRENCY", "1,8")
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def make_payload(size: int) -> bytes:
    if size <= 0:
        return b""
    # Deterministic printable body
    return (b"x" * size) if size < 16 else (b'{"pad":"' + (b"y" * (size - 10))[: size - 10] + b'"}')[:size]


@dataclass
class BenchResult:
    library: str
    scenario: str
    payload_bytes: int
    concurrency: int
    message_count: int
    wall_seconds: float
    msgs_per_sec: float
    latency_p50_ms: float | None = None
    latency_p99_ms: float | None = None
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_latencies_ms(samples_s: list[float]) -> tuple[float | None, float | None]:
    if not samples_s:
        return None, None
    xs = sorted(samples_s)
    def pct(p: float) -> float:
        if not xs:
            return 0.0
        idx = min(len(xs) - 1, max(0, math.ceil(p * len(xs)) - 1))
        return xs[idx] * 1000.0
    return pct(0.50), pct(0.99)


def timed_msgs_per_sec(count: int, wall: float) -> float:
    return count / wall if wall > 0 else 0.0


class Stopwatch:
    def __init__(self) -> None:
        self._t0 = 0.0
        self.elapsed = 0.0

    def __enter__(self) -> Stopwatch:
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self.elapsed = time.perf_counter() - self._t0
