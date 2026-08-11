"""Demo client: discover methods, subscribe to events, call RPC.

Run after the service is up::

    python examples/one_client_one_service/client.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EVENTS_EXCHANGE,
    MESH_EXCHANGE,
    SERVICE_NAME,
    cfg,
    routing_key,
)

from nuropb_rmq import (  # noqa: E402
    EventSubscriber,
    MeshRegistryViewer,
    RpcClient,
    Session,
)


async def main() -> None:
    config = cfg()
    viewer = MeshRegistryViewer(config)
    events_seen: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def on_event(method: str, params: object, _msg: object) -> None:
        print(f"[client] event {method} {params}", flush=True)
        await events_seen.put((method, params))

    subscriber = EventSubscriber(
        config,
        exchange=EVENTS_EXCHANGE,
        exchange_type="fanout",
        handler=on_event,
    )
    session = Session(config)

    try:
        await viewer.start()
        print("[client] waiting for registry advertisement…", flush=True)
        advert = None
        deadline = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline:
            advert = viewer.lookup(SERVICE_NAME)
            if advert is not None:
                break
            await asyncio.sleep(0.1)
        if advert is None:
            raise SystemExit(
                f"no advertisement for {SERVICE_NAME!r} within 10s — is service.py running?"
            )

        print(
            f"[client] discovered service={advert.service!r} methods={list(advert.methods)} "
            f"queue={advert.queue!r}",
            flush=True,
        )

        await subscriber.start()
        await session.start()
        client = RpcClient(session)

        # Prefer discovered method names; fall back to routing_key if already qualified.
        for short in advert.methods:
            key = routing_key(short)
            if short == "ping" or key.endswith(".ping"):
                result = await client.request(key, key, {}, exchange=MESH_EXCHANGE)
                print(f"[client] RPC {key} -> {result}", flush=True)
            elif short == "echo" or key.endswith(".echo"):
                result = await client.request(
                    key, key, {"hello": "world"}, exchange=MESH_EXCHANGE
                )
                print(f"[client] RPC {key} -> {result}", flush=True)

        # Drain events produced by the RPC handlers above.
        got = 0
        while got < 2:
            try:
                await asyncio.wait_for(events_seen.get(), timeout=5.0)
                got += 1
            except TimeoutError:
                print("[client] timed out waiting for events", flush=True)
                break
        print("[client] done", flush=True)
    finally:
        await session.close()
        await subscriber.close()
        await viewer.close()


if __name__ == "__main__":
    asyncio.run(main())
