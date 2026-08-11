"""Subscribe to the topic exchange ``nr.ex.logs``.

Default binding is ``logs.*``. Override with argv or ``NUROPB_RMQ_BINDING_KEY``::

    python examples/vanilla_topic/subscriber.py
    python examples/vanilla_topic/subscriber.py 'logs.error'
    NUROPB_RMQ_BINDING_KEY='#' python examples/vanilla_topic/subscriber.py
"""

from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import DEFAULT_BINDING_KEY, EXCHANGE, cfg  # noqa: E402

from nuropb_rmq import AmqpConnection  # noqa: E402


def _binding_key() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("NUROPB_RMQ_BINDING_KEY", DEFAULT_BINDING_KEY)


async def main() -> None:
    binding_key = _binding_key()
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
        await conn.exchange_declare(
            ch, EXCHANGE, exchange_type="topic", durable=True, auto_delete=False
        )
        queue = await conn.queue_declare(ch, "", exclusive=True, auto_delete=True)
        await conn.queue_bind(ch, queue, EXCHANGE, routing_key=binding_key)
        await conn.basic_consume(ch, queue)
        print(
            f"[subscriber] exchange={EXCHANGE!r} binding={binding_key!r} "
            f"queue={queue!r} (Ctrl-C to stop)",
            flush=True,
        )
        while not stop.is_set():
            try:
                msg = await conn.receive(timeout=0.5)
            except TimeoutError:
                continue
            text = msg.body.decode("utf-8", errors="replace")
            print(
                f"[subscriber] {msg.routing_key} -> {text!r}",
                flush=True,
            )
            await conn.basic_ack(ch, msg.delivery_tag)
    finally:
        await conn.close()
        print("[subscriber] stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
