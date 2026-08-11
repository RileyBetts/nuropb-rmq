"""Optional AMQP-backed mesh discovery registry (never a bind/auth authority).

Services may announce themselves on fanout exchange ``nr.mesh.registry``.
Viewers maintain an in-memory TTL map for discovery. Broker ACL and
``MeshService.assert_bind_allowed`` remain the only security gates.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, IncomingMessage

DEFAULT_REGISTRY_EXCHANGE = "nr.mesh.registry"
DEFAULT_ADVERTISE_TTL_S = 60.0
_REGISTRY_HEADER = "nr.registry"


@dataclass(frozen=True, slots=True)
class ServiceAdvertisement:
    """One mesh service announcement (discovery aid only)."""

    service: str
    methods: tuple[str, ...]
    instance_id: str
    queue: str
    exchange: str
    published_at: float
    ttl_s: float

    @property
    def expires_at(self) -> float:
        return self.published_at + self.ttl_s

    def is_expired(self, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    def to_wire(self) -> bytes:
        return json.dumps(
            {
                "service": self.service,
                "methods": list(self.methods),
                "instance_id": self.instance_id,
                "queue": self.queue,
                "exchange": self.exchange,
                "published_at": self.published_at,
                "ttl_s": self.ttl_s,
            },
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def from_wire(cls, body: bytes) -> ServiceAdvertisement:
        data = json.loads(body.decode("utf-8"))
        methods = data.get("methods") or []
        if not isinstance(methods, list) or not all(isinstance(m, str) for m in methods):
            raise ValueError("registry advertisement methods must be a list of strings")
        return cls(
            service=str(data["service"]),
            methods=tuple(methods),
            instance_id=str(data["instance_id"]),
            queue=str(data["queue"]),
            exchange=str(data["exchange"]),
            published_at=float(data["published_at"]),
            ttl_s=float(data["ttl_s"]),
        )


class AdvertisementStore:
    """In-memory map keyed by ``service`` (latest advert wins); drops expired entries."""

    def __init__(self) -> None:
        self._by_service: dict[str, ServiceAdvertisement] = {}

    def put(self, advert: ServiceAdvertisement) -> None:
        self._by_service[advert.service] = advert

    def _prune(self, now: float | None = None) -> None:
        t = now if now is not None else time.time()
        expired = [k for k, v in self._by_service.items() if v.is_expired(t)]
        for k in expired:
            del self._by_service[k]

    def lookup(self, service: str, *, now: float | None = None) -> ServiceAdvertisement | None:
        self._prune(now)
        return self._by_service.get(service)

    def list_services(self, *, now: float | None = None) -> list[ServiceAdvertisement]:
        self._prune(now)
        return sorted(self._by_service.values(), key=lambda a: a.service)


async def announce_on_connection(
    conn: AmqpConnection,
    *,
    channel_id: int,
    advert: ServiceAdvertisement,
    registry_exchange: str = DEFAULT_REGISTRY_EXCHANGE,
) -> None:
    """Declare registry fanout (if needed) and publish one advertisement."""
    await conn.exchange_declare(
        channel_id,
        registry_exchange,
        exchange_type="fanout",
        durable=True,
        auto_delete=False,
    )
    await conn.basic_publish(
        channel_id,
        advert.to_wire(),
        exchange=registry_exchange,
        routing_key="",
        properties={
            "content_type": "application/json",
            "headers": {_REGISTRY_HEADER: 1},
        },
    )


class MeshRegistryPublisher:
    """Standalone announcer (own connection) for mesh discovery."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        registry_exchange: str = DEFAULT_REGISTRY_EXCHANGE,
        channel_id: int = 1,
        ttl_s: float = DEFAULT_ADVERTISE_TTL_S,
    ) -> None:
        self.config = config or ConnectionConfig()
        self.conn = AmqpConnection(self.config)
        self.registry_exchange = registry_exchange
        self.channel_id = channel_id
        self.ttl_s = ttl_s
        self._started = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.registry_exchange,
            exchange_type="fanout",
            durable=True,
            auto_delete=False,
        )
        self._started = True

    async def close(self) -> None:
        self._started = False
        await self.conn.close()

    async def publish(self, advert: ServiceAdvertisement) -> None:
        if not self._started:
            raise RuntimeError("registry publisher not started")
        await announce_on_connection(
            self.conn,
            channel_id=self.channel_id,
            advert=advert,
            registry_exchange=self.registry_exchange,
        )

    def make_advertisement(
        self,
        *,
        service: str,
        methods: list[str] | tuple[str, ...],
        queue: str,
        exchange: str,
        instance_id: str | None = None,
    ) -> ServiceAdvertisement:
        return ServiceAdvertisement(
            service=service,
            methods=tuple(methods),
            instance_id=instance_id or uuid.uuid4().hex,
            queue=queue,
            exchange=exchange,
            published_at=time.time(),
            ttl_s=self.ttl_s,
        )


class MeshRegistryViewer:
    """Consume registry fanout into an in-memory discovery map."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        registry_exchange: str = DEFAULT_REGISTRY_EXCHANGE,
        channel_id: int = 1,
    ) -> None:
        self.config = config or ConnectionConfig()
        self.conn = AmqpConnection(self.config)
        self.registry_exchange = registry_exchange
        self.channel_id = channel_id
        self.store = AdvertisementStore()
        self.queue: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.registry_exchange,
            exchange_type="fanout",
            durable=True,
            auto_delete=False,
        )
        self.queue = await self.conn.queue_declare(
            self.channel_id,
            "",
            exclusive=True,
            auto_delete=True,
        )
        await self.conn.queue_bind(
            self.channel_id,
            self.queue,
            self.registry_exchange,
            routing_key="",
        )
        await self.conn.basic_consume(self.channel_id, self.queue)
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="mesh-registry-viewer")

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

    def lookup(self, service: str) -> ServiceAdvertisement | None:
        return self.store.lookup(service)

    def list_services(self) -> list[ServiceAdvertisement]:
        return self.store.list_services()

    async def _loop(self) -> None:
        try:
            while self._running:
                msg = await self.conn.receive(timeout=None)
                await self._handle(msg)
        except asyncio.CancelledError:
            raise

    async def _handle(self, msg: IncomingMessage) -> None:
        try:
            headers: dict[str, Any] = msg.properties.get("headers") or {}
            if headers.get(_REGISTRY_HEADER) not in (1, True, "1"):
                # Still accept bodies that decode as advertisements (lenient).
                pass
            advert = ServiceAdvertisement.from_wire(msg.body)
            if not advert.is_expired():
                self.store.put(advert)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            pass
        finally:
            await self.conn.basic_ack(self.channel_id, msg.delivery_tag)
