# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for mesh namespace binding."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.patterns.errors import BIND_REFUSED, RpcError
from nuropb_rmq.patterns.mesh import MeshService, NamespaceError, ServiceIdentity


def test_service_identity_valid() -> None:
    ident = ServiceIdentity("orders")
    assert ident.routing_key("ping") == "orders.ping"
    assert ident.assert_in_namespace("orders.ping") == "orders.ping"


def test_service_identity_rejects_bad_name() -> None:
    with pytest.raises(ValueError):
        ServiceIdentity("")
    with pytest.raises(ValueError):
        ServiceIdentity("bad name")


def test_namespace_refuse() -> None:
    ident = ServiceIdentity("orders")
    with pytest.raises(NamespaceError):
        ident.assert_in_namespace("other.ping")
    with pytest.raises(NamespaceError):
        ident.assert_in_namespace("orders.")


def test_mesh_assert_bind_allowed() -> None:
    mesh = MeshService(
        identity=ServiceIdentity("orders"),
        methods=["ping"],
    )
    assert mesh.assert_bind_allowed("orders.ping") == "orders.ping"
    with pytest.raises(RpcError) as ei:
        mesh.assert_bind_allowed("payments.charge")
    assert ei.value.code == BIND_REFUSED


@given(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=16),
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=16),
)
@settings(max_examples=40)
def test_pbt_routing_key_in_namespace(service: str, method: str) -> None:
    ident = ServiceIdentity(service)
    key = ident.routing_key(method)
    assert ident.assert_in_namespace(key) == key
    with pytest.raises(NamespaceError):
        ident.assert_in_namespace(f"x{service}.{method}")


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789", min_size=1, max_size=16))
@settings(max_examples=30)
def test_pbt_exact_service_key(service: str) -> None:
    """Lean `tryBind_exact_service`: bare service name is in-namespace."""
    ident = ServiceIdentity(service)
    assert ident.assert_in_namespace(service) == service
