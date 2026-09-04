# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Correspondence tests for Lean broker ACL profiles."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from nuropb_rmq.patterns.acl import (
    REPLY_HEX8,
    REPLY_PUBLISH_RESTRICTED_CLIENT,
    REPLY_PUBLISH_RESTRICTED_CLIENT_RE,
    REPLY_PUBLISH_RESTRICTED_SERVICE,
    REPLY_PUBLISH_RESTRICTED_SERVICE_RE,
    matches_regex,
    mesh_bind_namespaced,
    mesh_bind_namespaced_re,
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


def test_regex_profiles_agree_on_golden_names() -> None:
    goldens = (
        (REPLY_PUBLISH_RESTRICTED_CLIENT, REPLY_PUBLISH_RESTRICTED_CLIENT_RE, "nr.reply.victim"),
        (REPLY_PUBLISH_RESTRICTED_CLIENT, REPLY_PUBLISH_RESTRICTED_CLIENT_RE, "nr.reply.ownid"),
        (REPLY_PUBLISH_RESTRICTED_CLIENT, REPLY_PUBLISH_RESTRICTED_CLIENT_RE, "nr.mesh"),
        (REPLY_PUBLISH_RESTRICTED_SERVICE, REPLY_PUBLISH_RESTRICTED_SERVICE_RE, "nr.reply.abc"),
        (REPLY_PUBLISH_RESTRICTED_SERVICE, REPLY_PUBLISH_RESTRICTED_SERVICE_RE, "nr.mesh.events"),
    )
    for prefix, regex, name in goldens:
        assert prefix.can_publish(name) == regex.can_publish_regex(name)
        assert prefix.can_configure(name) == regex.can_configure_regex(name)
        assert prefix.can_read(name) == regex.can_read_regex(name)
    prefix = mesh_bind_namespaced("orders")
    regex = mesh_bind_namespaced_re("orders")
    for name in ("orders.ping", "payments.charge"):
        assert prefix.can_configure(name) == regex.can_configure_regex(name)


def test_regex_hex8_narrower_than_prefix() -> None:
    assert matches_regex(REPLY_HEX8, "nr.reply.abcd1234victim") is True
    assert matches_regex(REPLY_HEX8, "nr.reply.ZZZZzzzzvictim") is False
    assert REPLY_PUBLISH_RESTRICTED_CLIENT.can_configure("nr.reply.ZZZZzzzzvictim") is True
