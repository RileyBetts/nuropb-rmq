"""JSON-RPC 2.0 request/reply over AMQP (Session + exclusive reply queue)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from nuropb_rmq.patterns.envelope import (
    decode_request,
    decode_response,
    encode_error,
    encode_request,
    encode_result,
)
from nuropb_rmq.patterns.errors import (
    ID_COLLISION,
    INVALID_ENVELOPE,
    INVALID_ID,
    REQUEST_TIMEOUT,
    RpcError,
    make_error_data,
)
from nuropb_rmq.session.ids import IdCollisionError, InvalidIdError
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

Handler = Callable[[str, Any], Awaitable[Any] | Any]


class RpcClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def request(
        self,
        queue: str,
        method: str,
        params: Any = None,
        *,
        request_id: str | None = None,
    ) -> Any:
        if not self.session.reply_queue_open or self.session.reply_queue is None:
            raise RuntimeError("session not started")
        try:
            rid, fut = self.session.correlation.register(request_id)
        except InvalidIdError as exc:
            raise RpcError(
                INVALID_ID,
                str(exc),
                make_error_data(code=INVALID_ID, method=method),
            ) from exc
        except IdCollisionError as exc:
            raise RpcError(
                ID_COLLISION,
                str(exc),
                make_error_data(code=ID_COLLISION, method=method, correlation_id=request_id),
            ) from exc

        body = encode_request(method, params, rid)
        await self.session.conn.basic_publish(
            self.session.channel_id,
            body,
            routing_key=queue,
            properties={
                "content_type": "application/json",
                "correlation_id": rid,  # dual accessor: same value as JSON-RPC id
                "reply_to": self.session.reply_queue,
            },
        )
        try:
            msg: IncomingMessage = await self.session.wait_reply(rid, fut)
        except TimeoutError as exc:
            raise RpcError(
                REQUEST_TIMEOUT,
                "request timed out",
                make_error_data(code=REQUEST_TIMEOUT, retryable=True, correlation_id=rid, method=method),
                id=rid,
            ) from exc
        # Prefer AMQP correlation_id; body id must match (dual-accessor invariant)
        amqp_cid = msg.properties.get("correlation_id")
        if amqp_cid != rid:
            raise RpcError(
                INVALID_ENVELOPE,
                "reply correlation_id mismatch",
                make_error_data(code=INVALID_ENVELOPE, correlation_id=rid, method=method),
                id=rid,
            )
        return decode_response(msg.body)


class RpcServer:
    """Consumes a request queue and replies via reply_to / correlation_id."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        queue: str,
        handler: Handler,
        channel_id: int = 1,
    ) -> None:
        self.conn = AmqpConnection(config)
        self.queue = queue
        self.handler = handler
        self.channel_id = channel_id
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.queue_declare(self.channel_id, self.queue, durable=False)
        await self.conn.basic_consume(self.channel_id, self.queue)
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="rpc-server")

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
                await self._handle(msg)
        except asyncio.CancelledError:
            raise

    async def _handle(self, msg: IncomingMessage) -> None:
        reply_to = msg.properties.get("reply_to")
        corr = msg.properties.get("correlation_id")
        try:
            method, params, body_id = decode_request(msg.body)
            # Dual-accessor: AMQP correlation_id and JSON-RPC id must match
            if isinstance(corr, str) and corr != body_id:
                raise RpcError(
                    INVALID_ENVELOPE,
                    "correlation_id / jsonrpc id diverge",
                    make_error_data(code=INVALID_ENVELOPE, correlation_id=corr, method=method),
                )
            request_id = corr if isinstance(corr, str) else body_id
            result = self.handler(method, params)
            if asyncio.iscoroutine(result):
                result = await result
            out = encode_result(result, request_id)
        except RpcError as exc:
            request_id = corr if isinstance(corr, str) else exc.id
            out = encode_error(
                code=exc.code,
                message=exc.message,
                request_id=request_id,
                data=exc.data,
            )
        except Exception as exc:
            request_id = corr if isinstance(corr, str) else None
            out = encode_error(
                code=-32000,
                message="internal error",
                request_id=request_id,
                data=make_error_data(code=-32000, correlation_id=request_id),
            )
            _ = exc
        if isinstance(reply_to, str) and reply_to:
            rid = corr if isinstance(corr, str) else None
            props: dict[str, Any] = {"content_type": "application/json"}
            if rid:
                props["correlation_id"] = rid
            await self.conn.basic_publish(
                self.channel_id,
                out,
                routing_key=reply_to,
                properties=props,
            )
        await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
