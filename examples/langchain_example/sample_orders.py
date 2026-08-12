# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""In-memory order fixtures for the mesh orders.get_status service."""

from __future__ import annotations

from typing import Any

# Known orders the support agent can look up.
ORDERS: dict[str, dict[str, Any]] = {
    "ORD-1001": {
        "order_id": "ORD-1001",
        "status": "shipped",
        "carrier": "DHL",
        "eta": "2026-08-14",
        "tracking": "DHL1234567890",
    },
    "ORD-1002": {
        "order_id": "ORD-1002",
        "status": "processing",
        "carrier": None,
        "eta": "2026-08-18",
        "tracking": None,
    },
    "ORD-1003": {
        "order_id": "ORD-1003",
        "status": "cancelled",
        "carrier": None,
        "eta": None,
        "tracking": None,
    },
}

DEFAULT_ORDER_ID = "ORD-1001"


def lookup_order(order_id: str) -> dict[str, Any] | None:
    """Return a copy of the order status, or None if unknown."""
    order = ORDERS.get(order_id)
    if order is None:
        return None
    return dict(order)
