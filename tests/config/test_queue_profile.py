# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Unit tests for validated queue / delivery profiles."""

from __future__ import annotations

import pytest

from nuropb_rmq.config.queue_profile import (
    DELIVERY_NON_PERSISTENT,
    DELIVERY_PERSISTENT,
    DURABLE_AT_LEAST_ONCE,
    TRANSIENT_FAST_PATH,
    QueueProfile,
    durable_at_least_once,
    durable_classic,
    transient_fast_path,
)


def test_default_durable_at_least_once_shape() -> None:
    p = DURABLE_AT_LEAST_ONCE
    assert p.name == "durable-at-least-once"
    assert p.queue_type == "quorum"
    assert p.durable is True
    assert p.delivery_mode == DELIVERY_PERSISTENT
    args = p.declare_arguments()
    assert args["x-queue-type"] == "quorum"
    assert args["x-message-ttl"] == 60_000
    assert args["x-dead-letter-exchange"] == "nr.dlx"
    assert args["x-delivery-limit"] == 10


def test_refuse_durable_with_non_persistent() -> None:
    with pytest.raises(ValueError, match="delivery_mode=2"):
        QueueProfile(
            name="bad",
            queue_type="classic",
            durable=True,
            delivery_mode=DELIVERY_NON_PERSISTENT,
            message_ttl_ms=1000,
            dead_letter_exchange="dlx",
        )


def test_refuse_transient_with_persistent() -> None:
    with pytest.raises(ValueError, match="non-durable queue with persistent"):
        QueueProfile(
            name="bad",
            queue_type="classic",
            durable=False,
            delivery_mode=DELIVERY_PERSISTENT,
        )


def test_quorum_requires_delivery_limit() -> None:
    with pytest.raises(ValueError, match="x-delivery-limit"):
        QueueProfile(
            name="bad",
            queue_type="quorum",
            durable=True,
            delivery_mode=DELIVERY_PERSISTENT,
            message_ttl_ms=1000,
            dead_letter_exchange="dlx",
            delivery_limit=None,
        )


def test_classic_forbids_delivery_limit() -> None:
    with pytest.raises(ValueError, match="forbidden on classic"):
        durable_classic()
        QueueProfile(
            name="bad",
            queue_type="classic",
            durable=True,
            delivery_mode=DELIVERY_PERSISTENT,
            message_ttl_ms=1000,
            dead_letter_exchange="dlx",
            delivery_limit=5,
        )


def test_ttl_and_dlx_together() -> None:
    with pytest.raises(ValueError, match="together"):
        QueueProfile(
            name="bad",
            queue_type="classic",
            durable=True,
            delivery_mode=DELIVERY_PERSISTENT,
            message_ttl_ms=1000,
            dead_letter_exchange=None,
        )


def test_publish_refuses_non_persistent_on_durable() -> None:
    p = durable_at_least_once()
    with pytest.raises(ValueError, match="refusing non-persistent"):
        p.apply_publish_properties({"delivery_mode": 1})


def test_publish_applies_profile_mode() -> None:
    props = DURABLE_AT_LEAST_ONCE.apply_publish_properties({"content_type": "application/json"})
    assert props["delivery_mode"] == 2
    assert props["content_type"] == "application/json"


def test_transient_fast_path() -> None:
    p = transient_fast_path()
    assert p is not TRANSIENT_FAST_PATH or p.name == "transient-fast-path"
    assert p.declare_arguments() == {}
    assert p.apply_publish_properties()["delivery_mode"] == 1


def test_named_factories() -> None:
    assert durable_classic().queue_type == "classic"
    assert durable_classic().delivery_limit is None
