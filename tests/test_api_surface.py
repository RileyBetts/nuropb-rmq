# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Public API freeze snapshot (1.0)."""

from __future__ import annotations

from nuropb_rmq import api

# Frozen 1.0 surface. Additions are 1.x (CHANGELOG); removals require 2.0.
EXPECTED_ALL = [
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


def test_api_all_matches_freeze() -> None:
    assert list(api.__all__) == EXPECTED_ALL


def test_api_names_importable() -> None:
    for name in api.__all__:
        assert hasattr(api, name), name
