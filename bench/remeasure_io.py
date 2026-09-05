# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Python half of the Lean vs Python IO remasure.

Raw firehose is dual-connection. RPC topologies isolate session cost vs
``nr.mesh`` hop vs quorum. Exclusive + auto-delete for transient cells so
RabbitMQ 4 accepts the declare. Not an SLO.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid

from nuropb_rmq.config.queue_profile import durable_classic
from nuropb_rmq.patterns.mesh import DEFAULT_MESH_EXCHANGE, MeshService, ServiceIdentity
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig

CELLS = ("raw", "rpc", "mesh")


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


def parse_cells(raw: str) -> set[str]:
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    unknown = parts - set(CELLS)
    if unknown:
        raise ValueError(f"unknown cells {sorted(unknown)}; expected {CELLS}")
    return parts or set(CELLS)


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


async def rpc_run(count: int, size: int, overlap: bool, *, topo: str, conc: int = 8) -> None:
    c = cfg()
    mesh: MeshService | None = None
    server: RpcServer | None = None
    owned: AmqpConnection | None = None
    if topo == "classic":
        owned = AmqpConnection(c)
        await owned.connect()
        ch = await owned.open_channel(1)
        q = f"nr.bench.py.rpc.{uuid.uuid4().hex}"
        await owned.queue_declare(ch, q, exclusive=True, auto_delete=True)
        server = RpcServer(
            c, queue=q, handler=lambda _m, _p: {"ok": True}, conn=owned, declare_queue=False
        )
        await server.start()
        target, method, exchange = q, "echo", ""
        tag = "rpc_classic"
    elif topo in ("mesh_classic", "mesh_quorum"):
        svc = f"b{uuid.uuid4().hex[:12]}"
        profile = (
            durable_classic(dead_letter_exchange=f"nr.dlx.{svc}")
            if topo == "mesh_classic"
            else None
        )
        mesh = MeshService(
            c, identity=ServiceIdentity(svc), methods=["echo"], queue_profile=profile
        )
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=lambda _m, _p: {"ok": True})
        await server.start()
        target, method, exchange = f"{svc}.echo", "echo", DEFAULT_MESH_EXCHANGE
        tag = f"rpc_{topo}"
    else:
        raise ValueError(f"unknown topo {topo!r}")

    params = {"b": "y" * size}

    async def worker(n: int) -> None:
        sess = Session(c)
        await sess.start()
        cli = RpcClient(sess)
        try:
            for _ in range(n):
                await cli.request(target, method, params, exchange=exchange)
        finally:
            await sess.close()

    t0 = time.perf_counter()
    if overlap:
        per, rem = divmod(count, conc)
        await asyncio.gather(*[worker(per + (1 if i < rem else 0)) for i in range(conc)])
    else:
        await worker(count)
    wall = time.perf_counter() - t0
    label = f"{tag}_overlap" if overlap else tag
    print(f"python {label} size={size} count={count} msgs_per_sec={count / wall:.1f} wall={wall:.3f}")
    if server is not None:
        await server.close()
    if mesh is not None:
        await mesh.close()
    elif owned is not None:
        await owned.close()


async def run_kind(kind: str, cells: set[str]) -> None:
    if "raw" in cells:
        if kind == "amqps":
            await raw_serial(2000, 64)
            await raw_serial(2000, 1024)
            await raw_serial(1000, 16384)
        else:
            await raw_firehose(2000, 64)
            await raw_firehose(2000, 1024)
            await raw_firehose(1000, 16384)
    if "rpc" in cells:
        await rpc_run(200, 64, False, topo="classic")
        await rpc_run(400, 64, True, topo="classic")
    if "mesh" in cells:
        await rpc_run(200, 64, False, topo="mesh_classic")
        await rpc_run(400, 64, True, topo="mesh_classic")
        await rpc_run(200, 64, False, topo="mesh_quorum")
        await rpc_run(400, 64, True, topo="mesh_quorum")


def main() -> None:
    p = argparse.ArgumentParser(description="Python half of Lean vs Python IO remasure")
    p.add_argument("--kind", choices=("plain", "amqps"), default=os.environ.get("NUROPB_BENCH_KIND", "plain"))
    p.add_argument(
        "--cells",
        default=os.environ.get("NUROPB_BENCH_CELLS", "raw,rpc,mesh"),
        help="comma list: raw,rpc,mesh",
    )
    args = p.parse_args()
    asyncio.run(run_kind(args.kind, parse_cells(args.cells)))


if __name__ == "__main__":
    main()
