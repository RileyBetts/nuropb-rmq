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
from nuropb_rmq.patterns.errors import RpcError
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.patterns.mesh import DEFAULT_MESH_EXCHANGE, MeshService, ServiceIdentity
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer
from nuropb_rmq.session.reconnect import ReconnectCoordinator
from nuropb_rmq.session.session import Session
from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, TlsProfile
from nuropb_rmq.transport.tls_material import TlsMaterial

__all__ = [
    "AmqpConnection",
    "AuthConfig",
    "ConnectionConfig",
    "DEFAULT_MESH_EXCHANGE",
    "DLQ_TERMINAL",
    "DURABLE_AT_LEAST_ONCE",
    "DURABLE_CLASSIC",
    "DlqTimeoutProcessor",
    "EventPublisher",
    "EventSubscriber",
    "MeshService",
    "QueueProfile",
    "ReconnectCoordinator",
    "RpcClient",
    "RpcError",
    "RpcServer",
    "ServiceIdentity",
    "Session",
    "TRANSIENT_FAST_PATH",
    "TlsMaterial",
    "TlsProfile",
    "durable_at_least_once",
    "durable_classic",
    "transient_fast_path",
]
