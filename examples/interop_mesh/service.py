# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EVENTS_EXCHANGE, MESH_EXCHANGE, METHODS, SERVICE_NAME, cfg, routing_key  # noqa: E402
from nuropb_rmq import (  # noqa: E402
    EventPublisher,
    MeshRegistryPublisher,
    MeshService,
    RpcServer,
    ServiceIdentity,
)


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
        await events.publish("", "interop.request_handled", {"method": method})
        print(f"[service] handled {method} -> {result}", flush=True)
        return result

    stop = asyncio.Event()
    server: RpcServer | None = None

    def _stop(*_a: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _stop())

    try:
        await events.start()
        await registry.start()
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        print(
            f"[service] listening identity={SERVICE_NAME!r} methods={list(METHODS)} "
            f"mesh={MESH_EXCHANGE!r} events={EVENTS_EXCHANGE!r} (Ctrl-C to stop)",
            flush=True,
        )
        await stop.wait()
    finally:
        if server is not None:
            await server.close()
        await mesh.close()
        await registry.close()
        await events.close()


if __name__ == "__main__":
    asyncio.run(main())
