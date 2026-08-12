# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""JSON-RPC notification-shaped pub/sub over topic/fanout exchanges."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from nuropb_rmq.config.queue_profile import TRANSIENT_FAST_PATH, QueueProfile
from nuropb_rmq.patterns.envelope import decode_notification, encode_notification
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

ExchangeType = Literal["topic", "fanout"]
Handler = Callable[[str, Any, IncomingMessage], Awaitable[None] | None]


class EventPublisher:
    """Publishes JSON-RPC notifications to a topic or fanout exchange."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        exchange: str,
        exchange_type: ExchangeType = "topic",
        channel_id: int = 1,
        queue_profile: QueueProfile | None = None,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.channel_id = channel_id
        self.queue_profile = queue_profile or TRANSIENT_FAST_PATH
        self._started = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.exchange,
            exchange_type=self.exchange_type,
            auto_delete=True,
        )
        self._started = True

    async def close(self) -> None:
        self._started = False
        await self.conn.close()

    async def publish(self, routing_key: str, method: str, params: Any = None) -> None:
        if not self._started:
            raise RuntimeError("publisher not started")
        # Fanout ignores routing key at the broker; still allow callers to pass "".
        key = "" if self.exchange_type == "fanout" else routing_key
        body = encode_notification(method, params)
        await self.conn.basic_publish(
            self.channel_id,
            body,
            exchange=self.exchange,
            routing_key=key,
            properties={"content_type": "application/json"},
            queue_profile=self.queue_profile,
        )


class EventSubscriber:
    """Consumes notifications bound from a topic/fanout exchange."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        exchange: str,
        exchange_type: ExchangeType = "topic",
        handler: Handler,
        binding_key: str = "#",
        queue: str = "",
        exclusive: bool = True,
        auto_delete: bool = True,
        channel_id: int = 1,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.handler = handler
        self.binding_key = "" if exchange_type == "fanout" else binding_key
        self.queue_name = queue
        self.exclusive = exclusive
        self.auto_delete = auto_delete
        self.channel_id = channel_id
        self.queue: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.exchange,
            exchange_type=self.exchange_type,
            auto_delete=True,
        )
        self.queue = await self.conn.queue_declare(
            self.channel_id,
            self.queue_name,
            exclusive=self.exclusive,
            auto_delete=self.auto_delete,
        )
        await self.conn.queue_bind(
            self.channel_id,
            self.queue,
            self.exchange,
            routing_key=self.binding_key,
        )
        await self.conn.basic_consume(self.channel_id, self.queue)
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="event-subscriber")

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.conn.close()

    async def _loop(self) -> None:
        try:
            while self._running:
                msg = await self.conn.receive(timeout=None)
                await self._handle(msg)
        except asyncio.CancelledError:
            raise

    async def _handle(self, msg: IncomingMessage) -> None:
        try:
            method, params = decode_notification(msg.body)
            result = self.handler(method, params, msg)
            if asyncio.iscoroutine(result):
                await result
        finally:
            await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
