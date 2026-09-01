# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Public API surface for nuropb-rmq (stable imports)."""

from __future__ import annotations

from nuropb_rmq.config import (
    DLQ_TERMINAL,
    DURABLE_AT_LEAST_ONCE,
    DURABLE_CLASSIC,
    TRANSIENT_FAST_PATH,
    QueueProfile,
    durable_at_least_once,
    durable_classic,
    transient_fast_path,
)
from nuropb_rmq.patterns.context import AuthConfig
from nuropb_rmq.patterns.dlq_timeout import DlqTimeoutProcessor
from nuropb_rmq.patterns.errors import (
    BIND_REFUSED,
    CLAIMS_EXPIRED,
    CLAIMS_MISSING,
    CLAIMS_UNBOUND,
    CONNECTION_BLOCKED,
    CONNECTION_LOST,
    ID_COLLISION,
    INVALID_ENVELOPE,
    INVALID_ID,
    PUBLISH_NACK,
    PUBLISH_RETURNED,
    REQUEST_TIMEOUT,
    SERVER_ERROR,
    UNAUTHORIZED,
    RpcError,
)
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.patterns.mesh import (
    DEFAULT_MESH_EXCHANGE,
    MeshService,
    NamespaceError,
    ServiceIdentity,
)
from nuropb_rmq.patterns.registry import (
    DEFAULT_REGISTRY_EXCHANGE,
    MeshRegistryPublisher,
    MeshRegistryViewer,
    ServiceAdvertisement,
)
from nuropb_rmq.patterns.rpc import NackDelivery, RpcClient, RpcServer
from nuropb_rmq.session.reconnect import ReconnectCoordinator, ReconnectPolicy
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.confirm import PublishNack
from nuropb_rmq.transport.connection import (
    AmqpConnection,
    ConnectionBlockedError,
    ConnectionConfig,
    PublishReturned,
    ReturnedMessage,
    TlsProfile,
)
from nuropb_rmq.transport.tls_material import TlsMaterial

__all__ = [
    "AmqpConnection",
    "AuthConfig",
    "BIND_REFUSED",
    "CLAIMS_EXPIRED",
    "CLAIMS_MISSING",
    "CLAIMS_UNBOUND",
    "CONNECTION_BLOCKED",
    "CONNECTION_LOST",
    "ConnectionBlockedError",
    "ConnectionConfig",
    "DEFAULT_MESH_EXCHANGE",
    "DEFAULT_REGISTRY_EXCHANGE",
    "DLQ_TERMINAL",
    "DURABLE_AT_LEAST_ONCE",
    "DURABLE_CLASSIC",
    "DlqTimeoutProcessor",
    "EventPublisher",
    "EventSubscriber",
    "ID_COLLISION",
    "INVALID_ENVELOPE",
    "INVALID_ID",
    "MeshRegistryPublisher",
    "MeshRegistryViewer",
    "MeshService",
    "NackDelivery",
    "NamespaceError",
    "PUBLISH_NACK",
    "PUBLISH_RETURNED",
    "PublishNack",
    "PublishReturned",
    "QueueProfile",
    "REQUEST_TIMEOUT",
    "ReconnectCoordinator",
    "ReconnectPolicy",
    "ReturnedMessage",
    "RpcClient",
    "RpcError",
    "RpcServer",
    "SERVER_ERROR",
    "ServiceAdvertisement",
    "ServiceIdentity",
    "Session",
    "TRANSIENT_FAST_PATH",
    "TlsMaterial",
    "TlsProfile",
    "UNAUTHORIZED",
    "durable_at_least_once",
    "durable_classic",
    "transient_fast_path",
]
