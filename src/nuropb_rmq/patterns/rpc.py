"""JSON-RPC 2.0 request/reply over AMQP (Session + exclusive reply queue)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers
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
from nuropb_rmq.patterns.mesh import MeshService
from nuropb_rmq.session.ids import IdCollisionError, InvalidIdError
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

Handler = Callable[[str, Any], Awaitable[Any] | Any]


class RpcClient:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def request(
        self,
        target: str,
        method: str,
        params: Any = None,
        *,
        request_id: str | None = None,
        exchange: str = "",
        claims_token: str | None = None,
    ) -> Any:
        """Publish a JSON-RPC request.

        ``target`` is the default-exchange routing key (queue name) when
        ``exchange`` is empty, or the mesh routing key when ``exchange`` is set.
        """
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
        props: dict[str, Any] = {
            "content_type": "application/json",
            "correlation_id": rid,
            "reply_to": self.session.reply_queue,
        }
        if claims_token is not None:
            props = attach_claims_headers(props, claims_token)
        await self.session.conn.basic_publish(
            self.session.channel_id,
            body,
            exchange=exchange,
            routing_key=target,
            properties=props,
        )
        try:
            msg: IncomingMessage = await self.session.wait_reply(rid, fut)
        except TimeoutError as exc:
            raise RpcError(
                REQUEST_TIMEOUT,
                "request timed out",
                make_error_data(
                    code=REQUEST_TIMEOUT, retryable=True, correlation_id=rid, method=method
                ),
                id=rid,
            ) from exc
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
        auth: AuthConfig | None = None,
        conn: AmqpConnection | None = None,
        declare_queue: bool = True,
    ) -> None:
        self.conn = conn if conn is not None else AmqpConnection(config)
        self._owns_conn = conn is None
        self.queue = queue
        self.handler = handler
        self.channel_id = channel_id
        self.auth = auth
        self._declare_queue = declare_queue
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self._connected = False

    @classmethod
    def from_mesh(
        cls,
        mesh: MeshService,
        *,
        handler: Handler,
        auth: AuthConfig | None = None,
    ) -> RpcServer:
        """Consume a queue already declared/bound by ``MeshService.start()``."""
        if not mesh.started or mesh.queue is None:
            raise RuntimeError("mesh service not started")
        return cls(
            queue=mesh.queue,
            handler=handler,
            channel_id=mesh.channel_id,
            auth=auth,
            conn=mesh.conn,
            declare_queue=False,
        )

    async def start(self) -> None:
        if self._owns_conn:
            await self.conn.connect()
            await self.conn.open_channel(self.channel_id)
        elif not self.conn.sm.is_open:
            raise RuntimeError("shared connection is not open")
        if self._declare_queue:
            await self.conn.queue_declare(self.channel_id, self.queue, durable=False)
        await self.conn.basic_consume(self.channel_id, self.queue)
        self._connected = True
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
            self._task = None
        if self._owns_conn:
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
            if isinstance(corr, str) and corr != body_id:
                raise RpcError(
                    INVALID_ENVELOPE,
                    "correlation_id / jsonrpc id diverge",
                    make_error_data(code=INVALID_ENVELOPE, correlation_id=corr, method=method),
                )
            request_id = corr if isinstance(corr, str) else body_id
            if self.auth is not None:
                if not isinstance(request_id, str):
                    raise RpcError(
                        INVALID_ENVELOPE,
                        "correlation id required for auth",
                        make_error_data(code=INVALID_ENVELOPE, method=method),
                    )
                self.auth.verify_request(
                    method=method,
                    params=params,
                    correlation_id=request_id,
                    properties=msg.properties,
                )
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
