# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for mesh discovery registry (non-authoritative)."""

from __future__ import annotations

import time

import pytest

from nuropb_rmq.api import MeshRegistryPublisher
from nuropb_rmq.patterns.errors import BIND_REFUSED, RpcError
from nuropb_rmq.patterns.mesh import MeshService, ServiceIdentity
from nuropb_rmq.patterns.registry import AdvertisementStore, ServiceAdvertisement


def _advert(**overrides: object) -> ServiceAdvertisement:
    base: dict[str, object] = {
        "service": "orders",
        "methods": ("ping", "charge"),
        "instance_id": "abc",
        "queue": "nr.svc.orders",
        "exchange": "nr.mesh",
        "published_at": time.time(),
        "ttl_s": 60.0,
    }
    base.update(overrides)
    return ServiceAdvertisement(**base)  # type: ignore[arg-type]


def test_store_lookup_and_list() -> None:
    store = AdvertisementStore()
    a = _advert()
    store.put(a)
    assert store.lookup("orders") == a
    assert [x.service for x in store.list_services()] == ["orders"]


def test_store_ttl_expiry() -> None:
    store = AdvertisementStore()
    now = 1_000_000.0
    store.put(_advert(published_at=now - 10, ttl_s=5.0))
    assert store.lookup("orders", now=now) is None
    assert store.list_services(now=now) == []


def test_store_latest_wins() -> None:
    store = AdvertisementStore()
    now = time.time()
    store.put(_advert(instance_id="old", published_at=now - 1))
    store.put(_advert(instance_id="new", published_at=now))
    got = store.lookup("orders")
    assert got is not None
    assert got.instance_id == "new"


def test_wire_roundtrip() -> None:
    a = _advert(published_at=123.0, ttl_s=30.0)
    b = ServiceAdvertisement.from_wire(a.to_wire())
    assert b == a


def test_api_mesh_registry_publisher_advert_wire() -> None:
    pub = MeshRegistryPublisher(ttl_s=30.0)
    advert = pub.make_advertisement(
        service="orders",
        methods=["ping"],
        queue="nr.svc.orders",
        exchange="nr.mesh",
        instance_id="inst-1",
    )
    assert advert.service == "orders"
    assert advert.methods == ("ping",)
    assert advert.ttl_s == 30.0
    wire = advert.to_wire()
    assert ServiceAdvertisement.from_wire(wire) == advert


def test_assert_bind_allowed_does_not_use_registry() -> None:
    """Registry must never gate bind — even with announce enabled on MeshService."""
    mesh = MeshService(identity=ServiceIdentity("orders"), methods=["ping"], announce=True)
    assert mesh.assert_bind_allowed("orders.ping") == "orders.ping"
    with pytest.raises(RpcError) as ei:
        mesh.assert_bind_allowed("other.ping")
    assert ei.value.code == BIND_REFUSED
