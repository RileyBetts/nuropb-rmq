"""pika BlockingConnection runners for throughput comparison."""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import pika
from pika.exchange_type import ExchangeType

from bench.common import (
    BenchResult,
    Stopwatch,
    broker_host,
    broker_port,
    make_payload,
    summarize_latencies_ms,
    timed_msgs_per_sec,
)


def _params() -> pika.ConnectionParameters:
    return pika.ConnectionParameters(
        host=broker_host(),
        port=broker_port(),
        credentials=pika.PlainCredentials("guest", "guest"),
        heartbeat=60,
    )


def run_raw_publish_consume(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    queue = f"pk.bench.raw.{uuid.uuid4().hex}"
    body = make_payload(payload_bytes)
    latencies: list[float] = []
    lat_lock = threading.Lock()
    received = 0
    recv_lock = threading.Lock()
    done = threading.Event()

    cons = pika.BlockingConnection(_params())
    ch_c = cons.channel()
    ch_c.queue_declare(queue=queue, auto_delete=True)

    def on_message(ch, method, properties, body_in):  # type: ignore[no-untyped-def]
        nonlocal received
        headers = properties.headers or {}
        t0_us = headers.get("t0_us")
        if isinstance(t0_us, int):
            with lat_lock:
                latencies.append(time.perf_counter() - (t0_us / 1_000_000.0))
        ch.basic_ack(method.delivery_tag)
        with recv_lock:
            received += 1
            if received >= message_count:
                done.set()

    ch_c.basic_consume(queue=queue, on_message_callback=on_message)

    def consume_thread() -> None:
        while not done.is_set():
            cons.process_data_events(time_limit=0.1)

    t = threading.Thread(target=consume_thread, daemon=True)
    t.start()

    per = message_count // concurrency
    rem = message_count % concurrency

    def publish_worker(n: int) -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        for _ in range(n):
            t0_us = int(time.perf_counter() * 1_000_000)
            ch.basic_publish(
                exchange="",
                routing_key=queue,
                body=body,
                properties=pika.BasicProperties(headers={"t0_us": t0_us}),
            )
        conn.close()

    with Stopwatch() as sw:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futs = [
                pool.submit(publish_worker, per + (1 if i < rem else 0))
                for i in range(concurrency)
            ]
            for f in as_completed(futs):
                f.result()
        if not done.wait(timeout=max(30.0, message_count * 0.01)):
            raise TimeoutError("pika raw consume timed out")
    cons.close()

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="raw_publish_consume",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="BlockingConnection",
    )


def run_rpc_exclusive(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    """RPC using a real exclusive reply queue (parity with nuropb-rmq Session)."""
    req_q = f"pk.bench.rpc.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes)
    latencies: list[float] = []
    lat_lock = threading.Lock()

    # Server
    stop = threading.Event()

    def server_loop() -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        ch.queue_declare(queue=req_q, auto_delete=True)

        def on_req(ch, method, properties, body):  # type: ignore[no-untyped-def]
            reply_to = properties.reply_to
            corr = properties.correlation_id
            if reply_to and corr:
                ch.basic_publish(
                    exchange="",
                    routing_key=reply_to,
                    body=b'{"jsonrpc":"2.0","result":{"ok":true},"id":"'
                    + corr.encode()
                    + b'"}',
                    properties=pika.BasicProperties(correlation_id=corr),
                )
            ch.basic_ack(method.delivery_tag)

        ch.basic_consume(queue=req_q, on_message_callback=on_req)
        while not stop.is_set():
            conn.process_data_events(time_limit=0.1)
        conn.close()

    st = threading.Thread(target=server_loop, daemon=True)
    st.start()
    time.sleep(0.1)

    per = message_count // concurrency
    rem = message_count % concurrency

    def client_worker(n: int) -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        result = ch.queue_declare(queue="", exclusive=True, auto_delete=True)
        reply_q = result.method.queue
        pending: dict[str, float] = {}

        def on_reply(ch, method, properties, body):  # type: ignore[no-untyped-def]
            cid = properties.correlation_id
            t0 = pending.pop(cid, None)
            if t0 is not None:
                with lat_lock:
                    latencies.append(time.perf_counter() - t0)
            ch.basic_ack(method.delivery_tag)

        ch.basic_consume(queue=reply_q, on_message_callback=on_reply)
        for i in range(n):
            cid = f"{uuid.uuid4().hex}"
            pending[cid] = time.perf_counter()
            ch.basic_publish(
                exchange="",
                routing_key=req_q,
                body=payload,
                properties=pika.BasicProperties(
                    reply_to=reply_q,
                    correlation_id=cid,
                ),
            )
            # Wait for this reply (simple: process until pending empty for this id)
            while cid in pending:
                conn.process_data_events(time_limit=0.05)
        conn.close()

    try:
        with Stopwatch() as sw:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futs = [
                    pool.submit(client_worker, per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
                for f in as_completed(futs):
                    f.result()
    finally:
        stop.set()
        st.join(timeout=2)

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="rpc_exclusive_reply",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="BlockingConnection exclusive reply queue",
    )


def run_rpc_direct_reply_to(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
) -> BenchResult:
    """pika-only baseline using amq.rabbitmq.reply-to."""
    req_q = f"pk.bench.drep.{uuid.uuid4().hex}"
    payload = make_payload(payload_bytes)
    latencies: list[float] = []
    lat_lock = threading.Lock()
    stop = threading.Event()

    def server_loop() -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        ch.queue_declare(queue=req_q, auto_delete=True)

        def on_req(ch, method, properties, body):  # type: ignore[no-untyped-def]
            reply_to = properties.reply_to
            corr = properties.correlation_id
            if reply_to and corr:
                ch.basic_publish(
                    exchange="",
                    routing_key=reply_to,
                    body=b'{"ok":true}',
                    properties=pika.BasicProperties(correlation_id=corr),
                )
            ch.basic_ack(method.delivery_tag)

        ch.basic_consume(queue=req_q, on_message_callback=on_req)
        while not stop.is_set():
            conn.process_data_events(time_limit=0.1)
        conn.close()

    st = threading.Thread(target=server_loop, daemon=True)
    st.start()
    time.sleep(0.1)

    per = message_count // concurrency
    rem = message_count % concurrency

    def client_worker(n: int) -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        pending: dict[str, float] = {}

        def on_reply(ch, method, properties, body):  # type: ignore[no-untyped-def]
            cid = properties.correlation_id
            t0 = pending.pop(cid, None)
            if t0 is not None:
                with lat_lock:
                    latencies.append(time.perf_counter() - t0)
            # direct reply-to is no-ack

        ch.basic_consume(
            queue="amq.rabbitmq.reply-to",
            on_message_callback=on_reply,
            auto_ack=True,
        )
        for _ in range(n):
            cid = uuid.uuid4().hex
            pending[cid] = time.perf_counter()
            ch.basic_publish(
                exchange="",
                routing_key=req_q,
                body=payload,
                properties=pika.BasicProperties(
                    reply_to="amq.rabbitmq.reply-to",
                    correlation_id=cid,
                ),
            )
            while cid in pending:
                conn.process_data_events(time_limit=0.05)
        conn.close()

    try:
        with Stopwatch() as sw:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futs = [
                    pool.submit(client_worker, per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
                for f in as_completed(futs):
                    f.result()
    finally:
        stop.set()
        st.join(timeout=2)

    p50, p99 = summarize_latencies_ms(latencies)
    return BenchResult(
        library="pika",
        scenario="rpc_direct_reply_to",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        latency_p50_ms=p50,
        latency_p99_ms=p99,
        notes="BlockingConnection amq.rabbitmq.reply-to",
    )


def run_event_fanout(
    *,
    payload_bytes: int,
    concurrency: int,
    message_count: int,
    subscribers: int = 1,
) -> BenchResult:
    exchange = f"pk.bench.fanout.{uuid.uuid4().hex}"
    body = make_payload(payload_bytes)
    target = message_count * subscribers
    received = 0
    lock = threading.Lock()
    done = threading.Event()
    stop = threading.Event()

    def sub_loop() -> None:
        nonlocal received
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        ch.exchange_declare(exchange=exchange, exchange_type=ExchangeType.fanout, auto_delete=True)
        q = ch.queue_declare(queue="", exclusive=True, auto_delete=True).method.queue
        ch.queue_bind(queue=q, exchange=exchange)

        def on_msg(ch, method, properties, body_in):  # type: ignore[no-untyped-def]
            nonlocal received
            ch.basic_ack(method.delivery_tag)
            with lock:
                received += 1
                if received >= target:
                    done.set()

        ch.basic_consume(queue=q, on_message_callback=on_msg)
        while not stop.is_set() and not done.is_set():
            conn.process_data_events(time_limit=0.1)
        conn.close()

    threads = [threading.Thread(target=sub_loop, daemon=True) for _ in range(subscribers)]
    for th in threads:
        th.start()
    time.sleep(0.15)

    per = message_count // concurrency
    rem = message_count % concurrency

    def publish_worker(n: int) -> None:
        conn = pika.BlockingConnection(_params())
        ch = conn.channel()
        ch.exchange_declare(exchange=exchange, exchange_type=ExchangeType.fanout, auto_delete=True)
        for _ in range(n):
            ch.basic_publish(exchange=exchange, routing_key="", body=body)
        conn.close()

    try:
        with Stopwatch() as sw:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futs = [
                    pool.submit(publish_worker, per + (1 if i < rem else 0))
                    for i in range(concurrency)
                ]
                for f in as_completed(futs):
                    f.result()
            if not done.wait(timeout=max(30.0, message_count * 0.02)):
                raise TimeoutError("pika fanout consume timed out")
    finally:
        stop.set()
        for th in threads:
            th.join(timeout=2)

    return BenchResult(
        library="pika",
        scenario="event_fanout",
        payload_bytes=payload_bytes,
        concurrency=concurrency,
        message_count=message_count,
        wall_seconds=sw.elapsed,
        msgs_per_sec=timed_msgs_per_sec(message_count, sw.elapsed),
        notes=f"BlockingConnection subscribers={subscribers}",
        extra={"subscribers": subscribers, "deliveries": target},
    )
