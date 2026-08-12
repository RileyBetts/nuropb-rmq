# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Validated named queue / delivery profiles.

Durability-linked settings are one validated unit so durable queues never
silently accept non-persistent publishes (architecture Configuration Strategy).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

QueueType = Literal["quorum", "classic"]

# AMQP delivery_mode: 1 = non-persistent, 2 = persistent
DELIVERY_NON_PERSISTENT = 1
DELIVERY_PERSISTENT = 2


@dataclass(frozen=True, slots=True)
class QueueProfile:
    """Queue declare + publish delivery settings validated as a unit."""

    name: str
    queue_type: QueueType
    durable: bool
    delivery_mode: int
    message_ttl_ms: int | None = None
    dead_letter_exchange: str | None = None
    dead_letter_routing_key: str | None = None
    delivery_limit: int | None = None

    def __post_init__(self) -> None:
        if self.delivery_mode not in (DELIVERY_NON_PERSISTENT, DELIVERY_PERSISTENT):
            raise ValueError(f"delivery_mode must be 1 or 2, got {self.delivery_mode}")
        if self.durable and self.delivery_mode != DELIVERY_PERSISTENT:
            raise ValueError(
                f"profile {self.name!r}: durable queues require delivery_mode=2 "
                "(refuse non-persistent)"
            )
        if not self.durable and self.delivery_mode == DELIVERY_PERSISTENT:
            raise ValueError(
                f"profile {self.name!r}: non-durable queue with persistent messages "
                "is refused (likely misconfiguration)"
            )
        if self.queue_type == "quorum" and self.delivery_limit is None:
            raise ValueError(
                f"profile {self.name!r}: quorum requires x-delivery-limit"
            )
        if self.queue_type == "classic" and self.delivery_limit is not None:
            raise ValueError(
                f"profile {self.name!r}: x-delivery-limit is forbidden on classic queues"
            )
        if self.delivery_limit is not None and self.delivery_limit < 1:
            raise ValueError("delivery_limit must be >= 1")
        if self.message_ttl_ms is not None and self.message_ttl_ms < 1:
            raise ValueError("message_ttl_ms must be >= 1")
        has_ttl = self.message_ttl_ms is not None
        has_dlx = bool(self.dead_letter_exchange)
        if has_ttl != has_dlx:
            raise ValueError(
                f"profile {self.name!r}: TTL and dead-letter exchange must be set together"
            )
        if self.dead_letter_routing_key is not None and not has_dlx:
            raise ValueError(
                f"profile {self.name!r}: dead_letter_routing_key requires dead_letter_exchange"
            )

    @property
    def requires_dlx(self) -> bool:
        return bool(self.dead_letter_exchange)

    def declare_arguments(self) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if self.queue_type == "quorum":
            args["x-queue-type"] = "quorum"
        if self.message_ttl_ms is not None:
            args["x-message-ttl"] = int(self.message_ttl_ms)
        if self.dead_letter_exchange is not None:
            args["x-dead-letter-exchange"] = self.dead_letter_exchange
            if self.dead_letter_routing_key:
                args["x-dead-letter-routing-key"] = self.dead_letter_routing_key
        if self.delivery_limit is not None:
            args["x-delivery-limit"] = int(self.delivery_limit)
        return args

    def assert_delivery_mode(self, delivery_mode: int | None) -> int:
        """Return the effective delivery_mode; raise on profile disagreement."""
        if delivery_mode is None:
            return self.delivery_mode
        mode = int(delivery_mode)
        if self.durable and mode != DELIVERY_PERSISTENT:
            raise ValueError(
                f"profile {self.name!r}: refusing non-persistent publish "
                f"(delivery_mode={mode}) to a durable queue"
            )
        if not self.durable and mode == DELIVERY_PERSISTENT:
            raise ValueError(
                f"profile {self.name!r}: refusing persistent publish "
                f"to a non-durable queue"
            )
        if mode != self.delivery_mode:
            raise ValueError(
                f"profile {self.name!r}: delivery_mode {mode} disagrees with "
                f"profile delivery_mode {self.delivery_mode}"
            )
        return mode

    def apply_publish_properties(
        self,
        properties: dict[str, Any] | None = None,
        *,
        delivery_mode: int | None = None,
    ) -> dict[str, Any]:
        props = dict(properties or {})
        mode = self.assert_delivery_mode(
            delivery_mode if delivery_mode is not None else props.get("delivery_mode")
        )
        props["delivery_mode"] = mode
        return props


def durable_at_least_once(
    *,
    message_ttl_ms: int = 60_000,
    dead_letter_exchange: str = "nr.dlx",
    dead_letter_routing_key: str = "timeout",
    delivery_limit: int = 10,
) -> QueueProfile:
    """Default work-queue profile: quorum + persistent + TTL/DLX + delivery-limit."""
    if not dead_letter_exchange:
        raise ValueError("durable-at-least-once requires dead_letter_exchange")
    return QueueProfile(
        name="durable-at-least-once",
        queue_type="quorum",
        durable=True,
        delivery_mode=DELIVERY_PERSISTENT,
        message_ttl_ms=message_ttl_ms,
        dead_letter_exchange=dead_letter_exchange,
        dead_letter_routing_key=dead_letter_routing_key,
        delivery_limit=delivery_limit,
    )


def durable_classic(
    *,
    message_ttl_ms: int = 60_000,
    dead_letter_exchange: str = "nr.dlx",
    dead_letter_routing_key: str = "timeout",
) -> QueueProfile:
    """Explicit classic durable + persistent + TTL/DLX (no x-delivery-limit)."""
    if not dead_letter_exchange:
        raise ValueError("durable-classic requires dead_letter_exchange")
    return QueueProfile(
        name="durable-classic",
        queue_type="classic",
        durable=True,
        delivery_mode=DELIVERY_PERSISTENT,
        message_ttl_ms=message_ttl_ms,
        dead_letter_exchange=dead_letter_exchange,
        dead_letter_routing_key=dead_letter_routing_key,
        delivery_limit=None,
    )


def transient_fast_path() -> QueueProfile:
    """Lossy classic non-durable; never a silent default for work queues."""
    return QueueProfile(
        name="transient-fast-path",
        queue_type="classic",
        durable=False,
        delivery_mode=DELIVERY_NON_PERSISTENT,
    )


def dlq_terminal() -> QueueProfile:
    """Durable classic DLQ without further dead-lettering (timeout processor)."""
    return QueueProfile(
        name="dlq-terminal",
        queue_type="classic",
        durable=True,
        delivery_mode=DELIVERY_PERSISTENT,
    )


# Module-level defaults (factories so callers can still customize via functions).
DURABLE_AT_LEAST_ONCE = durable_at_least_once()
DURABLE_CLASSIC = durable_classic()
TRANSIENT_FAST_PATH = transient_fast_path()
DLQ_TERMINAL = dlq_terminal()
