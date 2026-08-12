# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""DLQ consumer: synthesize JSON-RPC timeout replies to original reply_to."""

from __future__ import annotations

import asyncio
from typing import Any

from nuropb_rmq.config.queue_profile import DLQ_TERMINAL, QueueProfile
from nuropb_rmq.patterns.envelope import encode_error
from nuropb_rmq.patterns.errors import REQUEST_TIMEOUT, make_error_data
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig


class DlqTimeoutProcessor:
    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        dlq_name: str,
        channel_id: int = 1,
        queue_profile: QueueProfile | None = None,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.dlq_name = dlq_name
        self.channel_id = channel_id
        self.queue_profile = queue_profile or DLQ_TERMINAL
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.queue_declare_profile(
            self.channel_id, self.dlq_name, self.queue_profile
        )
        await self.conn.basic_consume(self.channel_id, self.dlq_name)
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="dlq-timeout")

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.conn.close()

    async def _loop(self) -> None:
        try:
            while self._running:
                msg = await self.conn.receive(timeout=None)
                reply_to = msg.properties.get("reply_to")
                corr = msg.properties.get("correlation_id")
                if isinstance(reply_to, str) and reply_to and isinstance(corr, str):
                    body = encode_error(
                        code=REQUEST_TIMEOUT,
                        message="request timed out",
                        request_id=corr,
                        data=make_error_data(
                            code=REQUEST_TIMEOUT,
                            retryable=True,
                            correlation_id=corr,
                        ),
                    )
                    props: dict[str, Any] = {
                        "content_type": "application/json",
                        "correlation_id": corr,
                    }
                    await self.conn.basic_publish(
                        self.channel_id,
                        body,
                        routing_key=reply_to,
                        properties=props,
                        drain=False,
                    )
                await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
        except asyncio.CancelledError:
            raise
