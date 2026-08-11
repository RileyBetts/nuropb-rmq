"""Session: exclusive reply queue + correlation table over AmqpConnection."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from nuropb_rmq.session.correlation import CorrelationTable
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage


class Session:
    """Connection-scoped session with exclusive auto-delete reply queue."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        broker_timeout: bool = True,
        client_fallback_timeout: float | None = None,
    ) -> None:
        # broker_timeout=True: rely on broker TTL/DLX (no parallel client timer).
        # broker_timeout=False: mutually exclusive client-side fallback timeout.
        if broker_timeout and client_fallback_timeout is not None:
            raise ValueError(
                "client_fallback_timeout is mutually exclusive with broker_timeout=True"
            )
        if not broker_timeout and client_fallback_timeout is None:
            raise ValueError("client_fallback_timeout required when broker_timeout=False")
        self.conn = AmqpConnection(config)
        self.correlation = CorrelationTable()
        self.broker_timeout = broker_timeout
        self.client_fallback_timeout = client_fallback_timeout
        self.channel_id = 1
        self.connection_id = uuid.uuid4().hex
        self.reply_queue: str | None = None
        self._reply_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def reply_queue_open(self) -> bool:
        return self.reply_queue is not None and self._started

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        name = f"nr.reply.{self.connection_id}"
        self.reply_queue = await self.conn.queue_declare(
            self.channel_id,
            queue=name,
            exclusive=True,
            auto_delete=True,
        )
        await self.conn.basic_consume(self.channel_id, self.reply_queue)
        self._started = True
        self._reply_task = asyncio.create_task(self._reply_loop(), name="session-reply")

    async def close(self) -> None:
        self._started = False
        self.correlation.discard_all()
        if self._reply_task:
            self._reply_task.cancel()
            try:
                await self._reply_task
            except asyncio.CancelledError:
                pass
            self._reply_task = None
        self.reply_queue = None
        await self.conn.close()

    async def _reply_loop(self) -> None:
        try:
            while True:
                msg = await self.conn.receive(timeout=None)
                await self._on_reply(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.correlation.discard_all(exc)

    async def _on_reply(self, msg: IncomingMessage) -> None:
        cid = msg.properties.get("correlation_id")
        if isinstance(cid, str):
            self.correlation.resolve(cid, msg)
        await self.conn.basic_ack(self.channel_id, msg.delivery_tag)

    async def wait_reply(self, request_id: str, fut: asyncio.Future[Any]) -> IncomingMessage:
        if self.broker_timeout:
            return await fut
        assert self.client_fallback_timeout is not None
        try:
            return await asyncio.wait_for(fut, timeout=self.client_fallback_timeout)
        except TimeoutError as exc:
            self.correlation.fail(request_id, exc)
            raise
