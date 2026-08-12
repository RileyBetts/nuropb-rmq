# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Publish sample messages to the topic exchange ``nr.ex.logs``.

::

    python examples/vanilla_topic/publisher.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import EXCHANGE, SAMPLE_MESSAGES, cfg  # noqa: E402

from nuropb_rmq import AmqpConnection  # noqa: E402


async def main() -> None:
    conn = AmqpConnection(cfg())
    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.exchange_declare(
            ch, EXCHANGE, exchange_type="topic", durable=True, auto_delete=False
        )
        for routing_key, body in SAMPLE_MESSAGES:
            await conn.basic_publish(
                ch,
                body,
                exchange=EXCHANGE,
                routing_key=routing_key,
                properties={"content_type": "text/plain"},
            )
            print(f"[publisher] {routing_key} -> {body!r}", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
