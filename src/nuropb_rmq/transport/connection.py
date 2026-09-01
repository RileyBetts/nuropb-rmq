# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Asyncio TCP/TLS transport and AMQP connection orchestration."""

from __future__ import annotations

import asyncio
import os
import ssl
import tempfile
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nuropb_rmq.config.queue_profile import QueueProfile
from nuropb_rmq.protocol import methods as m
from nuropb_rmq.protocol.channel_sm import ChannelStateMachine
from nuropb_rmq.protocol.connection_sm import (
    ConnectionLost,
    ConnectionStateMachine,
    ProtocolError,
)
from nuropb_rmq.protocol.methods import (
    Method,
    decode_content_header,
    decode_method,
    encode_content_header,
    encode_method,
)
from nuropb_rmq.transport.confirm import ConfirmTracker
from nuropb_rmq.transport.frame import (
    DEFAULT_FRAME_MAX,
    PROTOCOL_HEADER,
    AmqpCodecError,
    Frame,
    FrameType,
    decode_frame,
    encode_frame,
    max_frame_payload,
)
from nuropb_rmq.transport.tls_material import TlsMaterial, TlsSecrets, resolve_tls_material
from nuropb_rmq.version import __version__

# Poison object waking blocked receive() after connection loss.
_LOSS_SENTINEL = object()


class ConnectionBlockedError(ProtocolError):
    """Publish refused because the broker sent connection.blocked."""


class PublishReturned(Exception):
    """Broker returned an unroutable mandatory publish (``basic.return``).

    Distinct from ``PublishNack``: confirms answer whether the broker accepted
    the message; return answers whether it was routable.
    """

    def __init__(
        self,
        reply_code: int,
        reply_text: str,
        *,
        exchange: str = "",
        routing_key: str = "",
        body: bytes = b"",
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.reply_code = reply_code
        self.reply_text = reply_text
        self.exchange = exchange
        self.routing_key = routing_key
        self.body = body
        self.properties = properties or {}
        super().__init__(
            f"basic.return {reply_code} {reply_text!r} "
            f"exchange={exchange!r} routing_key={routing_key!r}"
        )


@dataclass
class ReturnedMessage:
    """Unroutable mandatory publish delivered via ``basic.return`` + content."""

    reply_code: int
    reply_text: str
    exchange: str
    routing_key: str
    body: bytes
    properties: dict[str, Any]


class TlsProfile:
    VERIFY_FULL = "tls-verify-full"
    VERIFY_CUSTOM_SAN = "tls-verify-custom-san"
    INSECURE_DEV_ONLY = "tls-insecure-dev-only"


@dataclass
class ConnectionConfig:
    host: str = "127.0.0.1"
    port: int = 5672
    virtual_host: str = "/"
    username: str = "guest"
    password: str = "guest"
    heartbeat: int = 60
    frame_max: int = DEFAULT_FRAME_MAX
    tls: bool = False
    tls_profile: str = TlsProfile.VERIFY_FULL
    ca_file: str | None = None
    cert_file: str | None = None
    key_file: str | None = None
    # In-memory PEM (bytes or str). Mutually exclusive with the matching *_file per slot.
    ca_data: bytes | str | None = None
    cert_data: bytes | str | None = None
    key_data: bytes | str | None = None
    # Re-invoked on each connect() for rotation; fills slots then file/bytes fallback.
    tls_secrets: TlsSecrets | None = None
    # PKCS#12 (.p12/.pfx) → PEM slots via optional cryptography ([pkcs12] extra).
    pkcs12_file: str | None = None
    pkcs12_data: bytes | None = None
    pkcs12_password: bytes | str | None = None
    server_hostname: str | None = None
    custom_sans: list[str] = field(default_factory=list)
    # Optional connection.blocked / unblocked callbacks (reason str for blocked).
    on_connection_blocked: Callable[[str], None] | None = None
    on_connection_unblocked: Callable[[], None] | None = None
    # Observability for unroutable mandatory publishes (distinct from confirms).
    on_basic_return: Callable[[ReturnedMessage], None] | None = None

    def __repr__(self) -> str:
        def _pem(label: str, data: bytes | str | None) -> str:
            if data is None:
                return f"{label}=None"
            n = len(data.encode("utf-8") if isinstance(data, str) else data)
            return f"{label}=<{n} bytes>"

        return (
            "ConnectionConfig("
            f"host={self.host!r}, port={self.port}, virtual_host={self.virtual_host!r}, "
            f"username={self.username!r}, password=<redacted>, "
            f"heartbeat={self.heartbeat}, frame_max={self.frame_max}, "
            f"tls={self.tls}, tls_profile={self.tls_profile!r}, "
            f"ca_file={self.ca_file!r}, cert_file={self.cert_file!r}, key_file={self.key_file!r}, "
            f"{_pem('ca_data', self.ca_data)}, {_pem('cert_data', self.cert_data)}, "
            f"{_pem('key_data', self.key_data)}, "
            f"tls_secrets={'set' if self.tls_secrets is not None else None}, "
            f"pkcs12_file={self.pkcs12_file!r}, {_pem('pkcs12_data', self.pkcs12_data)}, "
            f"pkcs12_password=<redacted>, "
            f"server_hostname={self.server_hostname!r}, custom_sans={self.custom_sans!r})"
        )


@dataclass
class IncomingMessage:
    delivery_tag: int
    exchange: str
    routing_key: str
    body: bytes
    properties: dict[str, Any]
    redelivered: bool
    consumer_tag: str


class AmqpConnection:
    """Minimal AMQP 0-9-1 client: connect, channel, declare, publish, consume, ack."""

    def __init__(self, config: ConnectionConfig | None = None) -> None:
        self.config = config or ConnectionConfig()
        self.sm = ConnectionStateMachine()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()
        self._channels: dict[int, ChannelStateMachine] = {}
        self._waiters: dict[tuple[int, int, int], asyncio.Future[Method]] = {}
        self._deliveries: asyncio.Queue[IncomingMessage | object] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False
        self._lost_exc: BaseException | None = None
        self._on_loss: Callable[[BaseException], None] | None = None
        self.frame_max = self.config.frame_max
        # Resolved on each connect(); used for SASL EXTERNAL (any cert source).
        self._tls_material: TlsMaterial | None = None
        self._heartbeat_sec: int = 0
        self._last_peer_frame_at: float = 0.0
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._publish_blocked: bool = False
        self._confirm: dict[int, ConfirmTracker] = {}
        self._mandatory_tags: dict[int, deque[int]] = {}
        self._return_by_tag: dict[int, dict[int, ReturnedMessage]] = {}
        self._returns: asyncio.Queue[ReturnedMessage | object] = asyncio.Queue()

    def set_on_loss(self, callback: Callable[[BaseException], None] | None) -> None:
        """Register callback invoked once when the connection is lost."""
        self._on_loss = callback

    @property
    def is_lost(self) -> bool:
        return self._lost_exc is not None

    async def connect(self) -> None:
        # Secrets hook (if any) runs here — once per new TCP/TLS connection (rotation).
        # Invariant 7: single heartbeat policy, Lean-validated range 1..60.
        hb_cfg = int(self.config.heartbeat)
        if hb_cfg <= 0 or hb_cfg > 60:
            raise ValueError(f"heartbeat must be 1..60, got {hb_cfg}")
        ssl_ctx = None
        self._tls_material = None
        if self.config.tls:
            self._tls_material = await resolve_tls_material(self.config)
            ssl_ctx = self._build_ssl_context(self._tls_material)
        server_hostname = self.config.server_hostname or self.config.host
        self.sm.on_tcp_connected(tls=bool(ssl_ctx))
        self._reader, self._writer = await asyncio.open_connection(
            self.config.host,
            self.config.port,
            ssl=ssl_ctx,
            server_hostname=server_hostname if ssl_ctx else None,
        )
        if ssl_ctx:
            self.sm.on_tls_verified()
        self.sm.allow_amqp_header()
        assert self._writer is not None
        self._writer.write(PROTOCOL_HEADER)
        await self._writer.drain()
        self._reader_task = asyncio.create_task(self._read_loop(), name="amqp-read")
        start = await self._expect(0, m.CONNECTION, m.CONNECTION_START)
        self.sm.on_connection_start()
        mechanisms = str(start.args.get("mechanisms", ""))
        mechanism, response = self._select_sasl(mechanisms)
        # Invariant 3: SASL only after verified TLS when TLS configured (enforced by SM path)
        self.sm.assert_can_send_connection_method(m.CONNECTION_START_OK)
        await self._send_method(
            0,
            Method(
                m.CONNECTION,
                m.CONNECTION_START_OK,
                {
                    "client_properties": {"product": "nuropb-rmq", "version": __version__},
                    "mechanism": mechanism,
                    "response": response,
                    "locale": "en_US",
                },
            ),
        )
        self.sm.on_connection_start_ok_sent()
        tune = await self._expect(0, m.CONNECTION, m.CONNECTION_TUNE)
        self.sm.on_connection_tune()
        channel_max = int(tune.args.get("channel_max") or 2047)
        frame_max = int(tune.args.get("frame_max") or self.config.frame_max)
        if frame_max == 0:
            frame_max = self.config.frame_max
        self.frame_max = min(frame_max, self.config.frame_max)
        heartbeat = min(int(tune.args.get("heartbeat") or hb_cfg), hb_cfg)
        if heartbeat <= 0:
            heartbeat = hb_cfg
        # Cap at Lean inv7 upper bound even if broker advertises higher.
        heartbeat = min(heartbeat, 60)
        self.sm.assert_can_send_connection_method(m.CONNECTION_TUNE_OK)
        await self._send_method(
            0,
            Method(
                m.CONNECTION,
                m.CONNECTION_TUNE_OK,
                {"channel_max": channel_max, "frame_max": self.frame_max, "heartbeat": heartbeat},
            ),
        )
        self.sm.on_connection_tune_ok_sent(heartbeat=heartbeat)
        self.sm.assert_can_send_connection_method(m.CONNECTION_OPEN)
        await self._send_method(
            0,
            Method(
                m.CONNECTION,
                m.CONNECTION_OPEN,
                {"virtual_host": self.config.virtual_host, "capabilities": "", "insist": False},
            ),
        )
        self.sm.on_connection_open_sent()
        await self._expect(0, m.CONNECTION, m.CONNECTION_OPEN_OK)
        self.sm.on_connection_open_ok()
        self._start_heartbeat(heartbeat)

    def _start_heartbeat(self, heartbeat: int) -> None:
        """Send heartbeats and fail the connection if the peer goes silent."""
        self._stop_heartbeat()
        self._heartbeat_sec = max(0, int(heartbeat))
        if self._heartbeat_sec <= 0:
            return
        self._last_peer_frame_at = time.monotonic()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="amqp-heartbeat"
        )

    def _stop_heartbeat(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

    def _note_peer_frame(self) -> None:
        self._last_peer_frame_at = time.monotonic()

    async def _heartbeat_loop(self) -> None:
        interval = self._heartbeat_sec
        # Check twice per interval; miss threshold is 2× negotiated heartbeat.
        sleep_for = max(interval / 2.0, 0.05)
        try:
            while not self._closed and self._lost_exc is None:
                await asyncio.sleep(sleep_for)
                if self._closed or self._lost_exc is not None:
                    return
                silent_for = time.monotonic() - self._last_peer_frame_at
                if silent_for > interval * 2:
                    self._notify_loss(ConnectionLost("heartbeat timeout"))
                    if self._writer is not None:
                        try:
                            self._writer.close()
                        except Exception:
                            pass
                    return
                try:
                    await self._send_frame(Frame(FrameType.HEARTBEAT, 0, b""))
                except Exception as exc:
                    self._notify_loss(exc)
                    return
        except asyncio.CancelledError:
            raise

    def _build_ssl_context(self, material: TlsMaterial) -> ssl.SSLContext:
        profile = self.config.tls_profile
        if profile == TlsProfile.INSECURE_DEV_ONLY:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        if material.ca_pem is not None:
            ctx = ssl.create_default_context(cadata=material.ca_pem.decode("ascii"))
        else:
            ctx = ssl.create_default_context(cafile=None)
        if material.cert_pem is not None:
            self._load_cert_chain(ctx, material)
        if profile == TlsProfile.VERIFY_CUSTOM_SAN:
            # Loud named profile: require explicit SAN allowlist; still verify chain.
            if not self.config.custom_sans:
                raise ValueError("tls-verify-custom-san requires custom_sans allowlist")
            hostname = self.config.server_hostname or self.config.host
            if hostname not in self.config.custom_sans:
                raise ValueError(f"hostname {hostname!r} not in custom_sans allowlist")
        elif profile != TlsProfile.VERIFY_FULL:
            raise ValueError(f"unknown tls profile {profile!r}")
        return ctx

    @staticmethod
    def _load_cert_chain(ctx: ssl.SSLContext, material: TlsMaterial) -> None:
        """Load client cert/key from PEM bytes via short-lived 0o600 temp files."""
        assert material.cert_pem is not None
        cert_path = key_path = None
        try:
            with tempfile.NamedTemporaryFile("wb", delete=False) as cert_f:
                cert_f.write(material.cert_pem)
                cert_path = cert_f.name
            os.chmod(cert_path, 0o600)
            if material.key_pem is not None:
                with tempfile.NamedTemporaryFile("wb", delete=False) as key_f:
                    key_f.write(material.key_pem)
                    key_path = key_f.name
                os.chmod(key_path, 0o600)
            try:
                ctx.load_cert_chain(cert_path, key_path)
            except ssl.SSLError as exc:
                raise ValueError(
                    "invalid client certificate/key PEM (load_cert_chain failed)"
                ) from exc
        finally:
            for path in (cert_path, key_path):
                if path is not None:
                    try:
                        os.unlink(path)
                    except OSError:
                        pass

    def _select_sasl(self, mechanisms: str) -> tuple[str, bytes]:
        offered = {part.strip() for part in mechanisms.split() if part.strip()}
        # Prefer EXTERNAL when offered and client cert present from any source.
        has_client_cert = bool(self._tls_material and self._tls_material.has_client_cert)
        if "EXTERNAL" in offered and has_client_cert:
            return "EXTERNAL", b""
        if "PLAIN" not in offered:
            self.sm.reject(f"no supported SASL mechanism in {offered!r}")
        user = self.config.username.encode("utf-8")
        password = self.config.password.encode("utf-8")
        return "PLAIN", b"\x00" + user + b"\x00" + password

    async def open_channel(self, channel_id: int = 1) -> int:
        if not self.sm.is_open:
            raise ProtocolError("connection not open")
        if channel_id in self._channels:
            raise ProtocolError(f"channel {channel_id} already exists")
        ch = ChannelStateMachine(channel_id)
        self._channels[channel_id] = ch
        self._confirm[channel_id] = ConfirmTracker()
        self._mandatory_tags[channel_id] = deque()
        self._return_by_tag[channel_id] = {}
        ch.on_open_sent()
        await self._send_method(channel_id, Method(m.CHANNEL, m.CHANNEL_OPEN, {"out_of_band": ""}))
        await self._expect(channel_id, m.CHANNEL, m.CHANNEL_OPEN_OK)
        ch.on_open_ok()
        return channel_id

    async def confirm_select(self, channel_id: int) -> None:
        """Enable RabbitMQ publisher confirms on ``channel_id``."""
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        tracker = self._confirm.setdefault(channel_id, ConfirmTracker())
        if tracker.enabled:
            return
        await self._send_method(
            channel_id,
            Method(m.CONFIRM, m.CONFIRM_SELECT, {"nowait": False}),
        )
        await self._expect(channel_id, m.CONFIRM, m.CONFIRM_SELECT_OK)
        tracker.enable()

    async def queue_declare(
        self,
        channel_id: int,
        queue: str = "",
        *,
        durable: bool = False,
        exclusive: bool = False,
        auto_delete: bool = False,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        await self._send_method(
            channel_id,
            Method(
                m.QUEUE,
                m.QUEUE_DECLARE,
                {
                    "queue": queue,
                    "durable": durable,
                    "exclusive": exclusive,
                    "auto_delete": auto_delete,
                    "arguments": arguments or {},
                },
            ),
        )
        ok = await self._expect(channel_id, m.QUEUE, m.QUEUE_DECLARE_OK)
        return str(ok.args["queue"])

    async def ensure_profile_dlx(self, channel_id: int, profile: QueueProfile) -> None:
        """Declare the profile's dead-letter exchange when configured."""
        if not profile.requires_dlx or profile.dead_letter_exchange is None:
            return
        await self.exchange_declare(
            channel_id,
            profile.dead_letter_exchange,
            exchange_type="topic",
            durable=True,
            auto_delete=False,
        )

    async def queue_declare_profile(
        self,
        channel_id: int,
        queue: str,
        profile: QueueProfile,
        *,
        exclusive: bool = False,
        auto_delete: bool | None = None,
    ) -> str:
        """Declare a queue using a validated :class:`QueueProfile`."""
        if exclusive and profile.queue_type == "quorum":
            raise ValueError("quorum queues cannot be exclusive")
        if auto_delete is None:
            auto_delete = not profile.durable
        if auto_delete and profile.queue_type == "quorum":
            raise ValueError("quorum queues cannot be auto-delete")
        if auto_delete and profile.durable:
            raise ValueError(
                f"profile {profile.name!r}: durable queues must not be auto_delete"
            )
        await self.ensure_profile_dlx(channel_id, profile)
        return await self.queue_declare(
            channel_id,
            queue,
            durable=profile.durable,
            exclusive=exclusive,
            auto_delete=auto_delete,
            arguments=profile.declare_arguments(),
        )

    async def exchange_declare(
        self,
        channel_id: int,
        exchange: str,
        *,
        exchange_type: str = "fanout",
        durable: bool = False,
        auto_delete: bool = False,
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        await self._send_method(
            channel_id,
            Method(
                m.EXCHANGE,
                m.EXCHANGE_DECLARE,
                {
                    "exchange": exchange,
                    "type": exchange_type,
                    "durable": durable,
                    "auto_delete": auto_delete,
                    "arguments": {},
                },
            ),
        )
        await self._expect(channel_id, m.EXCHANGE, m.EXCHANGE_DECLARE_OK)

    async def queue_bind(
        self,
        channel_id: int,
        queue: str,
        exchange: str,
        *,
        routing_key: str = "",
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        await self._send_method(
            channel_id,
            Method(
                m.QUEUE,
                m.QUEUE_BIND,
                {"queue": queue, "exchange": exchange, "routing_key": routing_key, "arguments": {}},
            ),
        )
        await self._expect(channel_id, m.QUEUE, m.QUEUE_BIND_OK)

    async def basic_publish(
        self,
        channel_id: int,
        body: bytes,
        *,
        exchange: str = "",
        routing_key: str = "",
        properties: dict[str, Any] | None = None,
        drain: bool = True,
        queue_profile: QueueProfile | None = None,
        confirm: bool | None = None,
        mandatory: bool = False,
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        if self._publish_blocked:
            raise ConnectionBlockedError("connection.blocked — publish refused")
        props = properties
        if queue_profile is not None:
            props = queue_profile.apply_publish_properties(properties)

        tracker = self._confirm.get(channel_id)
        want_confirm = confirm
        if want_confirm is None:
            # Auto-enable confirms for durable profiles; wait if channel already in confirm mode.
            if queue_profile is not None and queue_profile.durable:
                want_confirm = True
            elif tracker is not None and tracker.enabled:
                want_confirm = True
            else:
                want_confirm = False
        if want_confirm:
            if tracker is None or not tracker.enabled:
                await self.confirm_select(channel_id)
                tracker = self._confirm[channel_id]
            assert tracker is not None
            tag, confirm_fut = tracker.register()
        else:
            tag, confirm_fut = None, None

        if mandatory and tag is not None:
            self._mandatory_tags.setdefault(channel_id, deque()).append(tag)

        # Coalesce method + content-header + body frames into one write burst.
        self._write_frame(
            Frame(
                FrameType.METHOD,
                channel_id,
                encode_method(
                    Method(
                        m.BASIC,
                        m.BASIC_PUBLISH,
                        {
                            "exchange": exchange,
                            "routing_key": routing_key,
                            "mandatory": mandatory,
                        },
                    )
                ),
            )
        )
        header = encode_content_header(class_id=m.BASIC, body_size=len(body), properties=props)
        self._write_frame(Frame(FrameType.HEADER, channel_id, header))
        payload_max = max_frame_payload(self.frame_max)
        if not body:
            self._write_frame(Frame(FrameType.BODY, channel_id, b""))
        else:
            offset = 0
            while offset < len(body):
                chunk = body[offset : offset + payload_max]
                self._write_frame(Frame(FrameType.BODY, channel_id, chunk))
                offset += len(chunk)
        if drain:
            await self._drain()
        if confirm_fut is not None:
            await confirm_fut
            if mandatory and tag is not None:
                returned = self._return_by_tag.get(channel_id, {}).pop(tag, None)
                if returned is not None:
                    raise PublishReturned(
                        returned.reply_code,
                        returned.reply_text,
                        exchange=returned.exchange,
                        routing_key=returned.routing_key,
                        body=returned.body,
                        properties=returned.properties,
                    )

    async def update_secret(self, new_secret: str | bytes, reason: str = "") -> None:
        """Rotate the connection authentication secret (AMQP ``connection.update-secret``).

        Thin round-trip: send the new secret, wait for ``update-secret-ok``, then
        store it on ``ConnectionConfig.password`` for subsequent reconnects.
        """
        if not self.sm.is_open:
            raise ProtocolError("connection not open")
        self.sm.assert_can_send_connection_method(m.CONNECTION_UPDATE_SECRET)
        await self._send_method(
            0,
            Method(
                m.CONNECTION,
                m.CONNECTION_UPDATE_SECRET,
                {"new_secret": new_secret, "reason": reason},
            ),
        )
        await self._expect(0, m.CONNECTION, m.CONNECTION_UPDATE_SECRET_OK)
        if isinstance(new_secret, bytes):
            self.config.password = new_secret.decode("utf-8")
        else:
            self.config.password = new_secret

    async def basic_consume(self, channel_id: int, queue: str, *, consumer_tag: str = "") -> str:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        await self._send_method(
            channel_id,
            Method(
                m.BASIC,
                m.BASIC_CONSUME,
                {
                    "queue": queue,
                    "consumer_tag": consumer_tag,
                    "no_ack": False,
                    "exclusive": False,
                    "arguments": {},
                },
            ),
        )
        ok = await self._expect(channel_id, m.BASIC, m.BASIC_CONSUME_OK)
        return str(ok.args["consumer_tag"])

    async def basic_cancel(self, channel_id: int, consumer_tag: str) -> str:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        await self._send_method(
            channel_id,
            Method(
                m.BASIC,
                m.BASIC_CANCEL,
                {"consumer_tag": consumer_tag, "nowait": False},
            ),
        )
        ok = await self._expect(channel_id, m.BASIC, m.BASIC_CANCEL_OK)
        return str(ok.args["consumer_tag"])

    async def basic_ack(
        self, channel_id: int, delivery_tag: int, *, drain: bool = True
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        self._write_frame(
            Frame(
                FrameType.METHOD,
                channel_id,
                encode_method(
                    Method(m.BASIC, m.BASIC_ACK, {"delivery_tag": delivery_tag, "multiple": False})
                ),
            )
        )
        if drain:
            await self._drain()

    async def basic_nack(
        self,
        channel_id: int,
        delivery_tag: int,
        *,
        requeue: bool = False,
        multiple: bool = False,
        drain: bool = True,
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        self._write_frame(
            Frame(
                FrameType.METHOD,
                channel_id,
                encode_method(
                    Method(
                        m.BASIC,
                        m.BASIC_NACK,
                        {
                            "delivery_tag": delivery_tag,
                            "multiple": multiple,
                            "requeue": requeue,
                        },
                    )
                ),
            )
        )
        if drain:
            await self._drain()

    async def basic_reject(
        self,
        channel_id: int,
        delivery_tag: int,
        *,
        requeue: bool = False,
        drain: bool = True,
    ) -> None:
        ch = self._channels[channel_id]
        ch.assert_open_for_ops()
        self._write_frame(
            Frame(
                FrameType.METHOD,
                channel_id,
                encode_method(
                    Method(
                        m.BASIC,
                        m.BASIC_REJECT,
                        {"delivery_tag": delivery_tag, "requeue": requeue},
                    )
                ),
            )
        )
        if drain:
            await self._drain()

    async def receive(self, timeout: float | None = 5.0) -> IncomingMessage:
        if self._lost_exc is not None:
            raise self._lost_exc
        if timeout is None:
            item = await self._deliveries.get()
        else:
            item = await asyncio.wait_for(self._deliveries.get(), timeout=timeout)
        if item is _LOSS_SENTINEL:
            raise self._lost_exc or ConnectionLost("connection lost")
        assert isinstance(item, IncomingMessage)
        return item

    async def receive_return(self, timeout: float | None = 5.0) -> ReturnedMessage:
        """Wait for a ``basic.return`` (unroutable mandatory publish)."""
        if self._lost_exc is not None:
            raise self._lost_exc
        if timeout is None:
            item = await self._returns.get()
        else:
            item = await asyncio.wait_for(self._returns.get(), timeout=timeout)
        if item is _LOSS_SENTINEL:
            raise self._lost_exc or ConnectionLost("connection lost")
        assert isinstance(item, ReturnedMessage)
        return item

    async def force_drop(self) -> None:
        """Abruptly drop the TCP connection (tests / simulated network loss)."""
        self._closed = True
        self._stop_heartbeat()
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self._notify_loss(ConnectionLost("connection dropped"))

    def _notify_loss(self, exc: BaseException) -> None:
        if self._lost_exc is not None:
            return
        if not isinstance(exc, ConnectionLost):
            exc = ConnectionLost(str(exc))
        self._lost_exc = exc
        self._fail_waiters()
        for tracker in self._confirm.values():
            tracker.fail_all(exc)
        self._mandatory_tags.clear()
        self._return_by_tag.clear()
        try:
            self._deliveries.put_nowait(_LOSS_SENTINEL)
        except Exception:
            pass
        try:
            self._returns.put_nowait(_LOSS_SENTINEL)
        except Exception:
            pass
        if self._on_loss is not None:
            try:
                self._on_loss(exc)
            except Exception:
                pass

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop_heartbeat()
        try:
            if self.sm.is_open and self._writer is not None:
                self.sm.begin_close()
                await self._send_method(
                    0,
                    Method(
                        m.CONNECTION,
                        m.CONNECTION_CLOSE,
                        {"reply_code": 200, "reply_text": "bye", "class_id": 0, "method_id": 0},
                    ),
                )
                try:
                    await asyncio.wait_for(self._expect(0, m.CONNECTION, m.CONNECTION_CLOSE_OK), 2)
                    self.sm.on_close_ok()
                except (TimeoutError, ProtocolError, AmqpCodecError):
                    self.sm.on_close_ok()
        finally:
            if self._reader_task:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
            if self._writer:
                self._writer.close()
                try:
                    await self._writer.wait_closed()
                except Exception:
                    pass

    async def _send_method(self, channel: int, method: Method) -> None:
        await self._send_frame(Frame(FrameType.METHOD, channel, encode_method(method)))

    def _write_frame(self, frame: Frame) -> None:
        if self._writer is None:
            raise ProtocolError("not connected")
        self._writer.write(encode_frame(frame, frame_max=self.frame_max))

    async def _drain(self) -> None:
        if self._writer is None:
            raise ProtocolError("not connected")
        await self._writer.drain()

    async def _send_frame(self, frame: Frame) -> None:
        self._write_frame(frame)
        await self._drain()

    async def _expect(self, channel: int, class_id: int, method_id: int) -> Method:
        key = (channel, class_id, method_id)
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Method] = loop.create_future()
        self._waiters[key] = fut
        try:
            return await asyncio.wait_for(fut, timeout=10)
        finally:
            self._waiters.pop(key, None)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        pending_content: dict[int, dict[str, Any]] = {}
        try:
            while not self._closed:
                chunk = await self._reader.read(65536)
                if not chunk:
                    self.sm.reject("broker closed connection")
                self._buffer.extend(chunk)
                while True:
                    try:
                        frame, nxt = decode_frame(self._buffer, frame_max=self.frame_max)
                    except AmqpCodecError as exc:
                        if "incomplete" in str(exc):
                            break
                        self.sm.reject(str(exc))
                    del self._buffer[:nxt]
                    self._note_peer_frame()
                    if frame.frame_type == FrameType.HEARTBEAT:
                        continue
                    if frame.frame_type == FrameType.METHOD:
                        method = decode_method(frame.payload)
                        if (
                            method.class_id == m.CONNECTION
                            and method.method_id == m.CONNECTION_SECURE
                        ):
                            self.sm.reject(
                                "connection.secure not supported "
                                "(unexpected SASL challenge after start-ok)"
                            )
                        if (
                            method.class_id == m.CONNECTION
                            and method.method_id == m.CONNECTION_BLOCKED
                        ):
                            reason = str(method.args.get("reason", ""))
                            self._publish_blocked = True
                            cb = self.config.on_connection_blocked
                            if cb is not None:
                                try:
                                    cb(reason)
                                except Exception:
                                    pass
                            continue
                        if (
                            method.class_id == m.CONNECTION
                            and method.method_id == m.CONNECTION_UNBLOCKED
                        ):
                            self._publish_blocked = False
                            cb_u = self.config.on_connection_unblocked
                            if cb_u is not None:
                                try:
                                    cb_u()
                                except Exception:
                                    pass
                            continue
                        if (
                            method.class_id == m.BASIC
                            and method.method_id == m.BASIC_DELIVER
                        ):
                            pending_content[frame.channel] = {
                                "deliver": method,
                                "properties": {},
                                "body": bytearray(),
                                "remaining": None,
                            }
                            continue
                        if (
                            method.class_id == m.BASIC
                            and method.method_id == m.BASIC_RETURN
                        ):
                            pending_content[frame.channel] = {
                                "return": method,
                                "properties": {},
                                "body": bytearray(),
                                "remaining": None,
                            }
                            continue
                        if (
                            method.class_id == m.BASIC
                            and method.method_id in (m.BASIC_ACK, m.BASIC_NACK)
                        ):
                            tracker = self._confirm.get(frame.channel)
                            if tracker is not None and tracker.enabled:
                                tag = int(method.args["delivery_tag"])
                                multiple = bool(method.args.get("multiple"))
                                self._clear_mandatory_tags(
                                    frame.channel, tag, multiple=multiple
                                )
                                if method.method_id == m.BASIC_ACK:
                                    tracker.on_ack(tag, multiple=multiple)
                                else:
                                    tracker.on_nack(tag, multiple=multiple)
                                continue
                        if (
                            method.class_id == m.CONNECTION
                            and method.method_id == m.CONNECTION_CLOSE
                        ):
                            # Fail closed: reply close-ok and tear down
                            try:
                                await self._send_method(
                                    0, Method(m.CONNECTION, m.CONNECTION_CLOSE_OK, {})
                                )
                            finally:
                                self.sm.reject(
                                    f"broker closed: {method.args.get('reply_text')}"
                                )
                        key = (frame.channel, method.class_id, method.method_id)
                        fut = self._waiters.get(key)
                        if fut and not fut.done():
                            fut.set_result(method)
                        continue
                    if frame.frame_type == FrameType.HEADER:
                        class_id, body_size, props = decode_content_header(frame.payload)
                        slot = pending_content.get(frame.channel)
                        if slot is None:
                            self.sm.reject("content header without deliver or return")
                        slot["properties"] = props
                        slot["remaining"] = body_size
                        slot["class_id"] = class_id
                        if body_size == 0:
                            self._finish_delivery(frame.channel, pending_content)
                        continue
                    if frame.frame_type == FrameType.BODY:
                        slot = pending_content.get(frame.channel)
                        if slot is None or slot["remaining"] is None:
                            self.sm.reject("body frame without header")
                        rem = int(slot["remaining"])
                        plen = len(frame.payload)
                        # Common path: single body frame — keep payload bytes as-is.
                        if rem == plen and not slot["body"]:
                            slot["body"] = frame.payload
                            slot["remaining"] = 0
                            self._finish_delivery(frame.channel, pending_content)
                            continue
                        body = slot["body"]
                        if isinstance(body, bytes):
                            body = bytearray(body)
                            slot["body"] = body
                        body.extend(frame.payload)
                        slot["remaining"] = rem - plen
                        if slot["remaining"] < 0:
                            self.sm.reject("body exceeded content header size")
                        if slot["remaining"] == 0:
                            self._finish_delivery(frame.channel, pending_content)
        except asyncio.CancelledError:
            raise
        except ProtocolError as exc:
            self._notify_loss(exc)
            raise
        except Exception as exc:
            try:
                self.sm.reject(str(exc))
            except ProtocolError as pe:
                self._notify_loss(pe)
            else:
                self._notify_loss(ConnectionLost(str(exc)))

    def _finish_delivery(self, channel: int, pending: dict[int, dict[str, Any]]) -> None:
        slot = pending.pop(channel)
        body = slot["body"]
        if not isinstance(body, bytes):
            body = bytes(body)
        if "return" in slot:
            self._finish_return(channel, slot["return"], body, dict(slot["properties"]))
            return
        deliver: Method = slot["deliver"]
        msg = IncomingMessage(
            delivery_tag=int(deliver.args["delivery_tag"]),
            exchange=str(deliver.args.get("exchange", "")),
            routing_key=str(deliver.args.get("routing_key", "")),
            body=body,
            properties=dict(slot["properties"]),
            redelivered=bool(deliver.args.get("redelivered")),
            consumer_tag=str(deliver.args.get("consumer_tag", "")),
        )
        self._deliveries.put_nowait(msg)

    def _finish_return(
        self,
        channel: int,
        method: Method,
        body: bytes,
        properties: dict[str, Any],
    ) -> None:
        returned = ReturnedMessage(
            reply_code=int(method.args.get("reply_code", 312)),
            reply_text=str(method.args.get("reply_text", "")),
            exchange=str(method.args.get("exchange", "")),
            routing_key=str(method.args.get("routing_key", "")),
            body=body,
            properties=properties,
        )
        tags = self._mandatory_tags.get(channel)
        if tags:
            tag = tags.popleft()
            self._return_by_tag.setdefault(channel, {})[tag] = returned
        cb = self.config.on_basic_return
        if cb is not None:
            try:
                cb(returned)
            except Exception:
                pass
        self._returns.put_nowait(returned)

    def _clear_mandatory_tags(self, channel: int, delivery_tag: int, *, multiple: bool) -> None:
        """Drop mandatory tags that were confirmed without a preceding return."""
        dq = self._mandatory_tags.get(channel)
        if not dq:
            return
        if multiple:
            remaining = deque(t for t in dq if t > delivery_tag)
            self._mandatory_tags[channel] = remaining
            return
        try:
            dq.remove(delivery_tag)
        except ValueError:
            pass

    def _fail_waiters(self) -> None:
        err = self._lost_exc or ProtocolError("connection failed")
        for fut in list(self._waiters.values()):
            if not fut.done():
                fut.set_exception(err)
