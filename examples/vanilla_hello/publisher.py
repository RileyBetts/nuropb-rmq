"""Publish a plain-text message to the durable hello queue.

::

    python examples/vanilla_hello/publisher.py
    python examples/vanilla_hello/publisher.py "custom body"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import QUEUE, cfg  # noqa: E402

from nuropb_rmq import AmqpConnection  # noqa: E402


async def main() -> None:
    body = " ".join(sys.argv[1:]).encode("utf-8") if len(sys.argv) > 1 else b"hello-nuropb-rmq"
    conn = AmqpConnection(cfg())
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare(ch, QUEUE, durable=True)
        await conn.basic_publish(
            ch,
            body,
            exchange="",
            routing_key=QUEUE,
            properties={"content_type": "text/plain", "delivery_mode": 2},
        )
        print(f"[publisher] sent {body!r} -> queue={QUEUE!r}", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
