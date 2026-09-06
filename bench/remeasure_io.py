# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Python half of the Lean vs Python IO remasure.

Raw firehose is dual-connection. RPC topologies isolate session cost vs
``nr.mesh`` hop vs quorum. Event fanout is one auto-delete exchange and
N exclusive subscribers; rate is publishes. Exclusive + auto-delete for
transient cells so RabbitMQ 4 accepts the declare. Not an SLO.

Wall is **first measured send → last complete** (ack / last fan-out copy /
RPC reply). Declare, bind, consume, confirm.select, session start, and one
warmup round-trip are outside the clock.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
import uuid

from nuropb_rmq.config.queue_profile import durable_classic
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.patterns.mesh import DEFAULT_MESH_EXCHANGE, MeshService, ServiceIdentity
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

CELLS = ("raw", "rpc", "mesh", "events", "events_m2m", "rpc_m2m")


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
    await c.basic_publish(
        ch, body, routing_key=q, properties={"content_type": "application/octet-stream"}
    )
    msg = await c.receive()
    await c.basic_ack(ch, msg.delivery_tag)
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

    await pub.basic_publish(
        ch_p, body, routing_key=q, properties={"content_type": "application/octet-stream"}
    )
    warm = await cons.receive()
    await cons.basic_ack(ch_c, warm.delivery_tag)
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
    n_clients = conc if overlap else 1
    clients: list[tuple[Session, RpcClient]] = []
    for _ in range(n_clients):
        sess = Session(c)
        await sess.start()
        clients.append((sess, RpcClient(sess)))
    for _sess, cli in clients:
        await cli.request(target, method, params, exchange=exchange)

    async def worker(cli: RpcClient, n: int) -> None:
        for _ in range(n):
            await cli.request(target, method, params, exchange=exchange)

    t0 = time.perf_counter()
    if overlap:
        per, rem = divmod(count, conc)
        await asyncio.gather(
            *[worker(clients[i][1], per + (1 if i < rem else 0)) for i in range(conc)]
        )
    else:
        await worker(clients[0][1], count)
    wall = time.perf_counter() - t0
    label = f"{tag}_overlap" if overlap else tag
    print(f"python {label} size={size} count={count} msgs_per_sec={count / wall:.1f} wall={wall:.3f}")
    for sess, _cli in clients:
        await sess.close()
    if server is not None:
        await server.close()
    if mesh is not None:
        await mesh.close()
    elif owned is not None:
        await owned.close()


async def event_fanout(count: int, size: int, subscribers: int) -> None:
    exchange = f"nr.bench.py.fanout.{uuid.uuid4().hex}"
    payload = "y" * size
    target = count * subscribers
    counter = 0
    lock = asyncio.Lock()
    done = asyncio.Event()

    needed = subscribers

    async def handler(_method: str, _params: object, _msg: IncomingMessage) -> None:
        nonlocal counter
        async with lock:
            counter += 1
            if counter >= needed:
                done.set()

    c = cfg()
    subs = [
        EventSubscriber(c, exchange=exchange, exchange_type="fanout", handler=handler)
        for _ in range(subscribers)
    ]
    for s in subs:
        await s.start()
    pub = EventPublisher(c, exchange=exchange, exchange_type="fanout")
    await pub.start()
    try:
        await pub.publish("", "bench.warmup", {"b": payload})
        await asyncio.wait_for(done.wait(), timeout=30)
        counter = 0
        done.clear()
        needed = target
        t0 = time.perf_counter()
        for _ in range(count):
            await pub.publish("", "bench.event", {"b": payload})
        await asyncio.wait_for(done.wait(), timeout=60)
        wall = time.perf_counter() - t0
    finally:
        await pub.close()
        for s in subs:
            await s.close()
    print(
        f"python event_fanout subs={subscribers} size={size} count={count} "
        f"msgs_per_sec={count / wall:.1f} wall={wall:.3f}"
    )


async def event_fanout_m2m(
    per_pub: int,
    size: int,
    publishers: int,
    subscribers: int,
    *,
    durable: bool,
) -> None:
    """P independent publishers × M subscribers. Rate is aggregate publishes."""
    exchange = f"nr.bench.py.m2m.{uuid.uuid4().hex}"
    payload = "y" * size
    total = per_pub * publishers
    target = total * subscribers
    counter = 0
    lock = asyncio.Lock()
    done = asyncio.Event()
    tag = uuid.uuid4().hex[:8]
    profile = (
        durable_classic(dead_letter_exchange=f"nr.dlx.m2m.{tag}") if durable else None
    )

    needed = subscribers

    async def handler(_method: str, _params: object, _msg: IncomingMessage) -> None:
        nonlocal counter
        async with lock:
            counter += 1
            if counter >= needed:
                done.set()

    c = cfg()
    subs = [
        EventSubscriber(
            c,
            exchange=exchange,
            exchange_type="fanout",
            handler=handler,
            queue=f"nr.bench.py.m2m.{tag}.{i}" if durable else "",
            durable=durable,
        )
        for i in range(subscribers)
    ]
    for s in subs:
        await s.start()
    pubs = [
        EventPublisher(
            c,
            exchange=exchange,
            exchange_type="fanout",
            queue_profile=profile,
        )
        for _ in range(publishers)
    ]
    for p in pubs:
        await p.start()

    async def pub_worker(pub: EventPublisher, n: int) -> None:
        for _ in range(n):
            await pub.publish("", "bench.event", {"b": payload})

    try:
        await pubs[0].publish("", "bench.warmup", {"b": payload})
        await asyncio.wait_for(done.wait(), timeout=30)
        counter = 0
        done.clear()
        needed = target
        t0 = time.perf_counter()
        await asyncio.gather(*[pub_worker(p, per_pub) for p in pubs])
        await asyncio.wait_for(done.wait(), timeout=90)
        wall = time.perf_counter() - t0
    finally:
        for p in pubs:
            await p.close()
        for s in subs:
            await s.close()
    dflag = 1 if durable else 0
    print(
        f"python event_fanout_m2m pubs={publishers} subs={subscribers} durable={dflag} "
        f"size={size} count={total} msgs_per_sec={total / wall:.1f} wall={wall:.3f}"
    )


async def rpc_m2m(*, clients: int = 4, servers: int = 2, per_client: int = 50, inflight: int = 8) -> None:
    """Independent async clients × competing mesh backends. Not the FIX path."""
    c = cfg()
    svc = f"m2m{uuid.uuid4().hex[:10]}"
    profile = durable_classic(dead_letter_exchange=f"nr.dlx.{svc}")
    meshes = [
        MeshService(c, identity=ServiceIdentity(svc), methods=["echo"], queue_profile=profile)
        for _ in range(servers)
    ]
    servers_rt: list[RpcServer] = []
    for mesh in meshes:
        await mesh.start()
        srv = RpcServer.from_mesh(mesh, handler=lambda _m, _p: {"ok": True})
        await srv.start()
        servers_rt.append(srv)
    target, method, exchange = f"{svc}.echo", "echo", DEFAULT_MESH_EXCHANGE
    params = {"b": "y" * 64}
    total = clients * per_client

    ready: list[tuple[Session, RpcClient]] = []
    for _ in range(clients):
        sess = Session(c)
        await sess.start()
        ready.append((sess, RpcClient(sess)))
    for _sess, cli in ready:
        await cli.request(target, method, params, exchange=exchange)

    async def client_worker(cli: RpcClient) -> None:
        left = per_client
        while left:
            n = min(inflight, left)
            await asyncio.gather(
                *[cli.request(target, method, params, exchange=exchange) for _ in range(n)]
            )
            left -= n

    t0 = time.perf_counter()
    try:
        await asyncio.gather(*[client_worker(cli) for _sess, cli in ready])
        wall = time.perf_counter() - t0
    finally:
        for sess, _cli in ready:
            await sess.close()
        for srv in servers_rt:
            await srv.close()
        for mesh in meshes:
            await mesh.close()
    print(
        f"python rpc_m2m clients={clients} servers={servers} inflight={inflight} "
        f"count={total} msgs_per_sec={total / wall:.1f} wall={wall:.3f}"
    )


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
    if "events" in cells:
        await event_fanout(2000, 64, 1)
        await event_fanout(2000, 64, 3)
    if "events_m2m" in cells:
        await event_fanout_m2m(200, 64, 4, 4, durable=False)
        await event_fanout_m2m(100, 64, 4, 4, durable=True)
    if "rpc_m2m" in cells:
        await rpc_m2m()


def main() -> None:
    p = argparse.ArgumentParser(description="Python half of Lean vs Python IO remasure")
    p.add_argument("--kind", choices=("plain", "amqps"), default=os.environ.get("NUROPB_BENCH_KIND", "plain"))
    p.add_argument(
        "--cells",
        default=os.environ.get("NUROPB_BENCH_CELLS", "raw,rpc,mesh"),
        help="comma list: raw,rpc,mesh,events,events_m2m,rpc_m2m",
    )
    args = p.parse_args()
    asyncio.run(run_kind(args.kind, parse_cells(args.cells)))


if __name__ == "__main__":
    main()
