# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""JSON-RPC notification-shaped pub/sub over topic/fanout exchanges.

Defaults are a **lossy live bus**. Durable fan-out (confirm + named durable
queue per consumer) is opt-in — see docs/concepts/events-durability.md.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from nuropb_rmq.config.queue_profile import TRANSIENT_FAST_PATH, QueueProfile
from nuropb_rmq.patterns.envelope import decode_notification, encode_notification
from nuropb_rmq.patterns.rpc import NackDelivery
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

ExchangeType = Literal["topic", "fanout"]
Handler = Callable[[str, Any, IncomingMessage], Awaitable[None] | None]


def _durable_exchange(profile: QueueProfile, override: bool | None) -> bool:
    return profile.durable if override is None else override


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
        durable_exchange: bool | None = None,
        mandatory: bool | None = None,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.channel_id = channel_id
        self.queue_profile = queue_profile or TRANSIENT_FAST_PATH
        self.durable_exchange = _durable_exchange(self.queue_profile, durable_exchange)
        self.mandatory = self.durable_exchange if mandatory is None else mandatory
        self._started = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.exchange,
            exchange_type=self.exchange_type,
            durable=self.durable_exchange,
            auto_delete=not self.durable_exchange,
        )
        if self.queue_profile.durable:
            await self.conn.confirm_select(self.channel_id)
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
            mandatory=self.mandatory,
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
        durable: bool = False,
        queue_profile: QueueProfile | None = None,
        durable_exchange: bool | None = None,
        ack_on_error: bool = True,
        channel_id: int = 1,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.exchange = exchange
        self.exchange_type = exchange_type
        self.handler = handler
        self.binding_key = "" if exchange_type == "fanout" else binding_key
        self.queue_name = queue
        self.durable = durable or bool(queue_profile is not None and queue_profile.durable)
        if self.durable:
            if not self.queue_name:
                raise ValueError("durable EventSubscriber requires queue=... (named per consumer)")
            exclusive = False
            auto_delete = False
        self.exclusive = exclusive
        self.auto_delete = auto_delete
        self.queue_profile = queue_profile
        self.durable_exchange = self.durable if durable_exchange is None else durable_exchange
        self.ack_on_error = ack_on_error
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
            durable=self.durable_exchange,
            auto_delete=not self.durable_exchange,
        )
        if self.queue_profile is not None:
            self.queue = await self.conn.queue_declare_profile(
                self.channel_id, self.queue_name, profile=self.queue_profile
            )
        else:
            self.queue = await self.conn.queue_declare(
                self.channel_id,
                self.queue_name,
                exclusive=self.exclusive,
                auto_delete=self.auto_delete,
                durable=self.durable,
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
        except Exception:
            await self.conn.basic_nack(self.channel_id, msg.delivery_tag, requeue=False)
            return
        try:
            result = self.handler(method, params, msg)
            if asyncio.iscoroutine(result):
                await result
        except NackDelivery as exc:
            await self.conn.basic_nack(
                self.channel_id, msg.delivery_tag, requeue=exc.requeue
            )
            return
        except Exception:
            if self.ack_on_error:
                await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
            else:
                await self.conn.basic_nack(self.channel_id, msg.delivery_tag, requeue=True)
            raise
        else:
            await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
