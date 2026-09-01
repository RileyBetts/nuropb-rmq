# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Correspondence tests for Lean broker ACL profiles."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.patterns.acl import (
    REPLY_PUBLISH_RESTRICTED_CLIENT,
    REPLY_PUBLISH_RESTRICTED_SERVICE,
    mesh_bind_namespaced,
)
from nuropb_rmq.patterns.mesh import ServiceIdentity


def test_forge_denied_client_cannot_publish_reply() -> None:
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_publish("nr.reply.victim") is False
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_configure("nr.reply.ownid") is True
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_read("nr.reply.ownid") is True
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_publish("nr.mesh") is True


def test_service_can_publish_reply() -> None:
    assert REPLY_PUBLISH_RESTRICTED_SERVICE.can_publish("nr.reply.abc") is True
    assert REPLY_PUBLISH_RESTRICTED_SERVICE.can_publish("nr.mesh.events") is True


def test_mesh_bind_namespaced_matches_try_bind() -> None:
    ident = ServiceIdentity("orders")
    perms = mesh_bind_namespaced("orders")
    ident.assert_in_namespace("orders.ping")
    assert perms.can_configure("orders.ping") is True
    assert perms.can_configure("payments.charge") is False


@given(st.text(min_size=1, max_size=24, alphabet=st.characters(min_codepoint=97, max_codepoint=122)))
@settings(max_examples=40)
def test_pbt_forge_never_writes_reply(suffix: str) -> None:
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_publish(f"nr.reply.{suffix}") is False
