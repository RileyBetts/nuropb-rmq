# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import QUEUE, cfg  # noqa: E402
from nuropb_rmq import AmqpConnection  # noqa: E402


async def main() -> None:
    conn = AmqpConnection(cfg())
    await conn.connect()
    ch = await conn.open_channel(1)
    queue = await conn.queue_declare(ch, QUEUE, durable=True)
    await conn.basic_consume(ch, queue)
    msg = await conn.receive(timeout=15)
    print(f"received {msg.body!r}", flush=True)
    await conn.basic_ack(ch, msg.delivery_tag)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
