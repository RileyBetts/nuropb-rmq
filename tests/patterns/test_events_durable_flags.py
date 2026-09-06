# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Constructor rules for durable event fan-out (no broker)."""

from __future__ import annotations

import pytest

from nuropb_rmq.config.queue_profile import durable_classic, transient_fast_path
from nuropb_rmq.patterns.events import EventPublisher, EventSubscriber


def test_publisher_default_is_lossy() -> None:
    pub = EventPublisher(exchange="nr.x")
    assert pub.durable_exchange is False
    assert pub.mandatory is False
    assert pub.queue_profile.name == "transient-fast-path"


def test_publisher_durable_profile_opts_in() -> None:
    pub = EventPublisher(exchange="nr.x", queue_profile=durable_classic())
    assert pub.durable_exchange is True
    assert pub.mandatory is True


def test_publisher_can_keep_ephemeral_exchange() -> None:
    pub = EventPublisher(
        exchange="nr.x",
        queue_profile=durable_classic(),
        durable_exchange=False,
        mandatory=False,
    )
    assert pub.durable_exchange is False
    assert pub.mandatory is False


def test_subscriber_durable_requires_named_queue() -> None:
    with pytest.raises(ValueError, match="named"):
        EventSubscriber(exchange="nr.x", handler=lambda *_: None, durable=True)


def test_subscriber_durable_forces_shared_queue() -> None:
    sub = EventSubscriber(
        exchange="nr.x",
        handler=lambda *_: None,
        queue="nr.fix.desk.a",
        durable=True,
    )
    assert sub.exclusive is False
    assert sub.auto_delete is False
    assert sub.durable_exchange is True


def test_transient_profile_does_not_force_durable() -> None:
    pub = EventPublisher(exchange="nr.x", queue_profile=transient_fast_path())
    assert pub.durable_exchange is False
