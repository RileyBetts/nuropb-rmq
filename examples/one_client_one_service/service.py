"""Demo mesh service: announce methods, handle RPC, publish events.

Run first (with RabbitMQ up)::

    python examples/one_client_one_service/service.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

# Allow running as ``python examples/one_client_one_service/service.py``
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EVENTS_EXCHANGE,
    MESH_EXCHANGE,
    METHODS,
    SERVICE_NAME,
    cfg,
    routing_key,
)

from nuropb_rmq import (  # noqa: E402
    EventPublisher,
    MeshRegistryPublisher,
    MeshService,
    RpcServer,
    ServiceIdentity,
)

# Re-announce so late-joining MeshRegistryViewer clients still see methods
# (fanout delivers only to queues bound at publish time).
_ANNOUNCE_EVERY_S = 3.0


async def main() -> None:
    config = cfg()
    events = EventPublisher(config, exchange=EVENTS_EXCHANGE, exchange_type="fanout")
    registry = MeshRegistryPublisher(config, ttl_s=30.0)
    mesh = MeshService(
        config,
        identity=ServiceIdentity(SERVICE_NAME),
        methods=list(METHODS),
        exchange=MESH_EXCHANGE,
        announce=True,
        announce_ttl_s=30.0,
    )

    async def handler(method: str, params: object) -> object:
        if method == routing_key("ping"):
            result: object = {"pong": True}
        elif method == routing_key("echo"):
            result = {"echo": params}
        else:
            raise ValueError(f"unknown method: {method}")
        await events.publish(
            "",
            "demo.request_handled",
            {"method": method, "params": params},
        )
        print(f"[service] handled {method} -> {result}", flush=True)
        return result

    server: RpcServer | None = None
    stop = asyncio.Event()
    heartbeat: asyncio.Task[None] | None = None

    def _request_stop(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: _request_stop())

    async def _announce_loop() -> None:
        assert mesh.queue is not None
        while not stop.is_set():
            advert = registry.make_advertisement(
                service=SERVICE_NAME,
                methods=METHODS,
                queue=mesh.queue,
                exchange=MESH_EXCHANGE,
                instance_id=mesh.instance_id,
            )
            await registry.publish(advert)
            try:
                await asyncio.wait_for(stop.wait(), timeout=_ANNOUNCE_EVERY_S)
            except TimeoutError:
                pass

    try:
        await events.start()
        await registry.start()
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        heartbeat = asyncio.create_task(_announce_loop(), name="registry-heartbeat")
        print(
            f"[service] listening identity={SERVICE_NAME!r} methods={list(METHODS)} "
            f"mesh={MESH_EXCHANGE!r} events={EVENTS_EXCHANGE!r} (Ctrl-C to stop)",
            flush=True,
        )
        await stop.wait()
    finally:
        stop.set()
        if heartbeat is not None:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass
        if server is not None:
            await server.close()
        await mesh.close()
        await registry.close()
        await events.close()
        print("[service] stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
