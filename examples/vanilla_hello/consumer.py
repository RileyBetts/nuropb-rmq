# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Consume plain-text messages from the durable hello queue.

::

    python examples/vanilla_hello/consumer.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import QUEUE, cfg  # noqa: E402

from nuropb_rmq import AmqpConnection  # noqa: E402


async def main() -> None:
    conn = AmqpConnection(cfg())
    stop = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: _request_stop())

    try:
        await conn.connect()
        ch = await conn.open_channel(1)
        await conn.queue_declare(ch, QUEUE, durable=True)
        await conn.basic_consume(ch, QUEUE)
        print(f"[consumer] waiting on queue={QUEUE!r} (Ctrl-C to stop)", flush=True)
        while not stop.is_set():
            try:
                msg = await conn.receive(timeout=0.5)
            except TimeoutError:
                continue
            text = msg.body.decode("utf-8", errors="replace")
            print(f"[consumer] received {text!r} routing_key={msg.routing_key!r}", flush=True)
            await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()
        print("[consumer] stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
