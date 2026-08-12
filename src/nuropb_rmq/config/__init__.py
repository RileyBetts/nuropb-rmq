# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Configuration profiles (queue/delivery, etc.)."""

from nuropb_rmq.config.queue_profile import (
    DELIVERY_NON_PERSISTENT,
    DELIVERY_PERSISTENT,
    DLQ_TERMINAL,
    DURABLE_AT_LEAST_ONCE,
    DURABLE_CLASSIC,
    TRANSIENT_FAST_PATH,
    QueueProfile,
    dlq_terminal,
    durable_at_least_once,
    durable_classic,
    transient_fast_path,
)

__all__ = [
    "DELIVERY_NON_PERSISTENT",
    "DELIVERY_PERSISTENT",
    "DLQ_TERMINAL",
    "DURABLE_AT_LEAST_ONCE",
    "DURABLE_CLASSIC",
    "TRANSIENT_FAST_PATH",
    "QueueProfile",
    "dlq_terminal",
    "durable_at_least_once",
    "durable_classic",
    "transient_fast_path",
]
