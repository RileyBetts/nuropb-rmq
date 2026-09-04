# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Python half of the Lean vs Python IO remasure.

Exclusive + auto-delete queues so RabbitMQ 4 accepts the declare. Not an SLO.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid

from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


def cfg() -> ConnectionConfig:
    tls = os.environ.get("NUROPB_RMQ_TLS") == "1"
    return ConnectionConfig(
        host=os.environ.get("NUROPB_RMQ_HOST", "127.0.0.1"),
        port=int(os.environ.get("NUROPB_RMQ_PORT", "5673")),
        tls=tls,
        ca_file=os.environ.get("NUROPB_RMQ_CA_FILE"),
        cert_file=os.environ.get("NUROPB_RMQ_CERT_FILE"),
        key_file=os.environ.get("NUROPB_RMQ_KEY_FILE"),
        server_hostname=os.environ.get("NUROPB_RMQ_SERVER_HOSTNAME", "localhost"),
    )


async def raw_serial(count: int, size: int) -> None:
    c = AmqpConnection(cfg())
    await c.connect()
    ch = await c.open_channel(1)
    q = f"nr.bench.py.raw.{uuid.uuid4().hex}"
    await c.queue_declare(ch, q, exclusive=True, auto_delete=True)
    await c.basic_consume(ch, q)
    body = b"x" * size
    t0 = time.perf_counter()
    for _ in range(count):
        await c.basic_publish(
            ch, body, routing_key=q, properties={"content_type": "application/octet-stream"}
        )
        msg = await c.receive()
        await c.basic_ack(ch, msg.delivery_tag)
    wall = time.perf_counter() - t0
    print(f"python raw_serial size={size} count={count} msgs_per_sec={count / wall:.1f} wall={wall:.3f}")
    await c.close()


async def raw_firehose(count: int, size: int) -> None:
    cons = AmqpConnection(cfg())
    pub = AmqpConnection(cfg())
    await cons.connect()
    await pub.connect()
    ch_c = await cons.open_channel(1)
    ch_p = await pub.open_channel(1)
    q = f"nr.bench.py.raw.{uuid.uuid4().hex}"
    await cons.queue_declare(ch_c, q, exclusive=True, auto_delete=True)
    await cons.basic_consume(ch_c, q)
    body = b"x" * size
    got = 0
    done = asyncio.Event()

    async def consume() -> None:
        nonlocal got
        while got < count:
            msg = await cons.receive()
            await cons.basic_ack(ch_c, msg.delivery_tag)
            got += 1
        done.set()

    t = asyncio.create_task(consume())
    t0 = time.perf_counter()
    for _ in range(count):
        await pub.basic_publish(
            ch_p, body, routing_key=q, properties={"content_type": "application/octet-stream"}
        )
    await asyncio.wait_for(done.wait(), timeout=60)
    wall = time.perf_counter() - t0
    await t
    print(f"python raw_firehose size={size} count={count} msgs_per_sec={count / wall:.1f} wall={wall:.3f}")
    await pub.close()
    await cons.close()


async def rpc_run(count: int, size: int, overlap: bool, conc: int = 8) -> None:
    q = f"nr.bench.py.rpc.{uuid.uuid4().hex}"
    conn = AmqpConnection(cfg())
    await conn.connect()
    ch = await conn.open_channel(1)
    await conn.queue_declare(ch, q, exclusive=True, auto_delete=True)
    server = RpcServer(
        cfg(), queue=q, handler=lambda _m, _p: {"ok": True}, conn=conn, declare_queue=False
    )
    await server.start()
    params = {"b": "y" * size}

    async def worker(n: int) -> None:
        sess = Session(cfg())
        await sess.start()
        cli = RpcClient(sess)
        try:
            for _ in range(n):
                await cli.request(q, "bench.echo", params)
        finally:
            await sess.close()

    t0 = time.perf_counter()
    if overlap:
        per, rem = divmod(count, conc)
        await asyncio.gather(*[worker(per + (1 if i < rem else 0)) for i in range(conc)])
    else:
        await worker(count)
    wall = time.perf_counter() - t0
    label = "rpc_overlap" if overlap else "rpc_serial"
    print(f"python {label} size={size} count={count} msgs_per_sec={count / wall:.1f} wall={wall:.3f}")
    await server.close()
    await conn.close()


async def run_kind(kind: str) -> None:
    if kind == "amqps":
        await raw_serial(2000, 64)
        await raw_serial(2000, 1024)
        await raw_serial(1000, 16384)
        await rpc_run(200, 64, False)
        await rpc_run(400, 64, True)
        return
    await raw_firehose(2000, 64)
    await raw_firehose(2000, 1024)
    await raw_firehose(1000, 16384)
    await rpc_run(200, 64, False)
    await rpc_run(400, 64, True)


def main() -> None:
    p = argparse.ArgumentParser(description="Python half of Lean vs Python IO remasure")
    p.add_argument("--kind", choices=("plain", "amqps"), default=os.environ.get("NUROPB_BENCH_KIND", "plain"))
    args = p.parse_args()
    asyncio.run(run_kind(args.kind))


if __name__ == "__main__":
    main()
