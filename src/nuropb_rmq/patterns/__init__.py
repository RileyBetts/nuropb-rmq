# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Messaging patterns (RPC, events, mesh, claims)."""

from nuropb_rmq.patterns.context import AuthConfig, attach_claims_headers
from nuropb_rmq.patterns.errors import RpcError
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber
from nuropb_rmq.patterns.mesh import MeshService, ServiceIdentity
from nuropb_rmq.patterns.rpc import RpcClient, RpcServer

__all__ = [
    "AuthConfig",
    "EventPublisher",
    "EventSubscriber",
    "MeshService",
    "RpcClient",
    "RpcError",
    "RpcServer",
    "ServiceIdentity",
    "attach_claims_headers",
]
