"""Mesh service registration/binding (broker-native, namespaced).

Permission profile (deployment prerequisite): ``mesh-bind-namespaced`` —
the broker user may only bind/consume under the service identity's
``<service>.*`` routing-key namespace. The library refuses out-of-namespace
binds client-side; broker ACL remains the hard gate. No app-level
registration authority in v1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from nuropb_rmq.patterns.errors import BIND_REFUSED, RpcError, make_error_data
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig

_SAFE_SERVICE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_SAFE_METHOD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")

DEFAULT_MESH_EXCHANGE = "nr.mesh"


class NamespaceError(ValueError):
    """Routing key or method outside the service identity namespace."""


@dataclass(frozen=True, slots=True)
class ServiceIdentity:
    """Logical service name that owns a routing-key namespace."""

    service: str

    def __post_init__(self) -> None:
        if not _SAFE_SERVICE.match(self.service):
            raise ValueError(
                "service must be 1..63 chars in [A-Za-z0-9._-] starting alphanumeric"
            )

    @property
    def namespace_prefix(self) -> str:
        return f"{self.service}."

    def routing_key(self, method: str) -> str:
        if not _SAFE_METHOD.match(method):
            raise ValueError("method name invalid for mesh routing key")
        return f"{self.service}.{method}"

    def assert_in_namespace(self, routing_key: str) -> str:
        if not isinstance(routing_key, str) or not routing_key:
            raise NamespaceError("routing key required")
        if routing_key == self.service or routing_key.startswith(self.namespace_prefix):
            # Reject path escape / empty method segment
            if routing_key.startswith(self.namespace_prefix):
                rest = routing_key[len(self.namespace_prefix) :]
                if not rest or ".." in routing_key:
                    raise NamespaceError(f"routing key outside namespace: {routing_key}")
            return routing_key
        raise NamespaceError(f"routing key outside namespace: {routing_key}")


class MeshService:
    """Declare request queue and bind only namespaced ``service.method`` keys."""

    def __init__(
        self,
        config: ConnectionConfig | None = None,
        *,
        identity: ServiceIdentity,
        methods: Sequence[str],
        exchange: str = DEFAULT_MESH_EXCHANGE,
        queue: str | None = None,
        channel_id: int = 1,
    ) -> None:
        if not methods:
            raise ValueError("methods must be non-empty")
        self.config = config or ConnectionConfig()
        self.conn = AmqpConnection(self.config)
        self.identity = identity
        self.exchange = exchange
        self.channel_id = channel_id
        self.queue_name = queue or f"nr.svc.{identity.service}"
        self.routing_keys: list[str] = []
        for method in methods:
            key = identity.routing_key(method)
            identity.assert_in_namespace(key)
            self.routing_keys.append(key)
        self.queue: str | None = None
        self._started = False

    def assert_bind_allowed(self, routing_key: str) -> str:
        """Client-side guardrail before issuing queue.bind (SpeC++ / fail-closed)."""
        try:
            return self.identity.assert_in_namespace(routing_key)
        except NamespaceError as exc:
            raise RpcError(
                BIND_REFUSED,
                str(exc),
                make_error_data(code=BIND_REFUSED, method=routing_key),
            ) from exc

    async def start(self) -> str:
        """Declare exchange + queue, bind namespaced keys. Returns queue name."""
        await self.conn.connect()
        await self.conn.open_channel(self.channel_id)
        await self.conn.exchange_declare(
            self.channel_id,
            self.exchange,
            exchange_type="direct",
            auto_delete=False,
        )
        self.queue = await self.conn.queue_declare(
            self.channel_id,
            self.queue_name,
            durable=False,
            exclusive=False,
            auto_delete=True,
        )
        for key in self.routing_keys:
            self.assert_bind_allowed(key)
            await self.conn.queue_bind(
                self.channel_id,
                self.queue,
                self.exchange,
                routing_key=key,
            )
        self._started = True
        return self.queue

    async def close(self) -> None:
        self._started = False
        await self.conn.close()

    async def rebind(self) -> str:
        """Close old connection and redeclare namespace binds on a fresh connection.

        Callers must restart RpcServer.from_mesh after rebind (v1 fail-fast;
        no transparent consumer resume).
        """
        try:
            await self.close()
        except Exception:
            pass
        self.conn = AmqpConnection(self.config)
        self.queue = None
        return await self.start()

    @property
    def started(self) -> bool:
        return self._started and self.queue is not None
