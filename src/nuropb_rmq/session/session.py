# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Session: exclusive reply queue + correlation table over AmqpConnection."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from nuropb_rmq.config.queue_profile import QueueProfile
from nuropb_rmq.patterns.errors import CONNECTION_LOST, RpcError, make_error_data
from nuropb_rmq.protocol.connection_sm import ConnectionLost
from nuropb_rmq.session.correlation import CorrelationTable
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

if TYPE_CHECKING:
    from nuropb_rmq.session.reconnect import ReconnectPolicy


def _connection_lost_error(exc: BaseException | None = None) -> RpcError:
    msg = str(exc) if exc else "connection lost"
    return RpcError(
        CONNECTION_LOST,
        msg,
        make_error_data(code=CONNECTION_LOST, retryable=True),
    )


@dataclass(slots=True)
class ParkedPublish:
    """In-flight RPC publish retained across a park-and-retry reconnect."""

    exchange: str
    routing_key: str
    body: bytes
    properties: dict[str, Any]
    queue_profile: QueueProfile | None = None
    mandatory: bool = True
    confirm: bool | None = None


class Session:
    """Connection-scoped session with exclusive auto-delete reply queue."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        broker_timeout: bool = True,
        client_fallback_timeout: float | None = None,
        fail_outstanding: bool | None = None,
        reconnect_policy: ReconnectPolicy | None = None,
    ) -> None:
        # broker_timeout=True: rely on broker TTL/DLX (no parallel client timer).
        # broker_timeout=False: mutually exclusive client-side fallback timeout.
        if broker_timeout and client_fallback_timeout is not None:
            raise ValueError(
                "client_fallback_timeout is mutually exclusive with broker_timeout=True"
            )
        if not broker_timeout and client_fallback_timeout is None:
            raise ValueError("client_fallback_timeout required when broker_timeout=False")
        if reconnect_policy is None:
            from nuropb_rmq.session.reconnect import ReconnectPolicy as _RP

            reconnect_policy = _RP(
                fail_outstanding=False if fail_outstanding is None else fail_outstanding
            )
        elif fail_outstanding is not None and fail_outstanding != reconnect_policy.fail_outstanding:
            raise ValueError("fail_outstanding does not match reconnect_policy.fail_outstanding")
        self.config = config or ConnectionConfig()
        self.conn = AmqpConnection(self.config)
        self.correlation = CorrelationTable()
        self.broker_timeout = broker_timeout
        self.client_fallback_timeout = client_fallback_timeout
        self.reconnect_policy = reconnect_policy
        self.fail_outstanding = reconnect_policy.fail_outstanding
        self.channel_id = 1
        self.connection_id = uuid.uuid4().hex
        self.epoch = 0
        self.reply_queue: str | None = None
        self._reply_task: asyncio.Task[None] | None = None
        self._started = False
        self._loss_handled = False
        self._parked: dict[str, ParkedPublish] = {}
        self._reconnect_lock = asyncio.Lock()
        self._auto_reconnect_task: asyncio.Task[None] | None = None

    @property
    def reply_queue_open(self) -> bool:
        return self.reply_queue is not None and self._started

    def remember_publish(self, request_id: str, envelope: ParkedPublish) -> None:
        """Retain a successful publish so park-and-retry can republish it."""
        self._parked[request_id] = envelope

    def forget_publish(self, request_id: str) -> None:
        self._parked.pop(request_id, None)

    def _wire_loss_handler(self) -> None:
        self.conn.set_on_loss(self._on_connection_lost)

    def _fail_outstanding(self, exc: BaseException | None = None) -> None:
        self.correlation.discard_all(_connection_lost_error(exc))
        self._parked.clear()

    def _on_connection_lost(self, exc: BaseException) -> None:
        if self._loss_handled:
            return
        self._loss_handled = True
        self._started = False
        self.reply_queue = None
        if self.fail_outstanding:
            self._fail_outstanding(exc)
            return
        # Park: keep correlation futures + envelopes; auto-reconnect.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._auto_reconnect_task is None or self._auto_reconnect_task.done():
            self._auto_reconnect_task = loop.create_task(
                self._park_reconnect(), name="session-park-reconnect"
            )

    async def _park_reconnect(self) -> None:
        from nuropb_rmq.session.reconnect import ReconnectCoordinator

        try:
            await ReconnectCoordinator(self.reconnect_policy).reconnect(self)
        except Exception as exc:
            self._fail_outstanding(exc)

    async def start(self) -> None:
        self._loss_handled = False
        self._wire_loss_handler()
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
        self._parked.clear()
        if self._auto_reconnect_task and not self._auto_reconnect_task.done():
            self._auto_reconnect_task.cancel()
            try:
                await self._auto_reconnect_task
            except (asyncio.CancelledError, Exception):
                pass
            self._auto_reconnect_task = None
        await self._stop_reply_task()
        self.reply_queue = None
        await self.conn.close()

    async def _stop_reply_task(self) -> None:
        if self._reply_task:
            self._reply_task.cancel()
            try:
                await self._reply_task
            except asyncio.CancelledError:
                pass
            self._reply_task = None

    async def _teardown_for_reconnect(self) -> None:
        """Drop the old connection; fail or park outstanding per policy."""
        self._started = False
        if self.fail_outstanding:
            self._fail_outstanding()
        await self._stop_reply_task()
        self.reply_queue = None
        try:
            await self.conn.close()
        except Exception:
            pass

    async def _republish_parked(self) -> None:
        if self.reply_queue is None:
            return
        from nuropb_rmq.patterns.errors import CONNECTION_BLOCKED, PUBLISH_NACK, PUBLISH_RETURNED
        from nuropb_rmq.transport.confirm import PublishNack
        from nuropb_rmq.transport.connection import ConnectionBlockedError, PublishReturned

        for rid, env in list(self._parked.items()):
            if rid not in self.correlation:
                self.forget_publish(rid)
                continue
            props = dict(env.properties)
            props["reply_to"] = self.reply_queue
            props["correlation_id"] = rid
            try:
                await self.conn.basic_publish(
                    self.channel_id,
                    env.body,
                    exchange=env.exchange,
                    routing_key=env.routing_key,
                    properties=props,
                    queue_profile=env.queue_profile,
                    mandatory=env.mandatory,
                    confirm=env.confirm,
                )
            except (PublishNack, PublishReturned, ConnectionBlockedError) as exc:
                self.forget_publish(rid)
                mapped: BaseException = exc
                if isinstance(exc, PublishReturned):
                    mapped = RpcError(
                        PUBLISH_RETURNED,
                        str(exc),
                        make_error_data(
                            code=PUBLISH_RETURNED, retryable=True, correlation_id=rid
                        ),
                        id=rid,
                    )
                elif isinstance(exc, PublishNack):
                    mapped = RpcError(
                        PUBLISH_NACK,
                        str(exc),
                        make_error_data(code=PUBLISH_NACK, retryable=True, correlation_id=rid),
                        id=rid,
                    )
                else:
                    mapped = RpcError(
                        CONNECTION_BLOCKED,
                        str(exc),
                        make_error_data(
                            code=CONNECTION_BLOCKED, retryable=True, correlation_id=rid
                        ),
                        id=rid,
                    )
                self.correlation.fail(rid, mapped)

    async def reconnect(self) -> None:
        """Open a new connection epoch with a fresh exclusive reply queue.

        Default (park): outstanding RpcClient futures stay pending and are
        republished with the new ``reply_to``. Fail-fast policy completes them
        with CONNECTION_LOST first. MeshService / RpcServer must still be
        rebound/restarted by the caller.
        """
        async with self._reconnect_lock:
            if self.reply_queue_open:
                return
            await self._teardown_for_reconnect()
            self.conn = AmqpConnection(self.config)
            self.connection_id = uuid.uuid4().hex
            self.epoch += 1
            await self.start()
            if not self.fail_outstanding:
                await self._republish_parked()

    async def _reply_loop(self) -> None:
        try:
            while True:
                msg = await self.conn.receive(timeout=None)
                await self._on_reply(msg)
        except asyncio.CancelledError:
            raise
        except ConnectionLost as exc:
            self._on_connection_lost(exc)
        except Exception as exc:
            self._fail_outstanding(exc)

    async def _on_reply(self, msg: IncomingMessage) -> None:
        cid = msg.properties.get("correlation_id")
        if isinstance(cid, str):
            self.correlation.resolve(cid, msg)
            self.forget_publish(cid)
        await self.conn.basic_ack(self.channel_id, msg.delivery_tag)

    async def wait_reply(self, request_id: str, fut: asyncio.Future[Any]) -> IncomingMessage:
        if self.broker_timeout:
            return await fut
        assert self.client_fallback_timeout is not None
        try:
            return await asyncio.wait_for(fut, timeout=self.client_fallback_timeout)
        except TimeoutError as exc:
            self.correlation.fail(request_id, exc)
            self.forget_publish(request_id)
            raise
