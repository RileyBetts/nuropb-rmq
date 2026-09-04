# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EVENTS_EXCHANGE, MESH_EXCHANGE, SERVICE_NAME, cfg, routing_key  # noqa: E402
from nuropb_rmq import EventSubscriber, RpcClient, Session  # noqa: E402


async def main() -> None:
    config = cfg()
    events_seen: asyncio.Queue[tuple[str, object]] = asyncio.Queue()

    async def on_event(method: str, params: object, _msg: object) -> None:
        print(f"[client] event {method} {params}", flush=True)
        await events_seen.put((method, params))

    subscriber = EventSubscriber(
        config, exchange=EVENTS_EXCHANGE, exchange_type="fanout", handler=on_event
    )
    session = Session(config)
    try:
        await subscriber.start()
        await session.start()
        client = RpcClient(session)
        for short in ("ping", "echo"):
            key = routing_key(short)
            params: object = {} if short == "ping" else {"hello": "world"}
            result = await client.request(key, key, params, exchange=MESH_EXCHANGE)
            print(f"[client] RPC {key} -> {result}", flush=True)
        try:
            await asyncio.wait_for(events_seen.get(), timeout=5.0)
        except TimeoutError:
            print("[client] timed out waiting for events", flush=True)
        print("[client] done", flush=True)
    finally:
        await session.close()
        await subscriber.close()


if __name__ == "__main__":
    _ = SERVICE_NAME
    asyncio.run(main())
