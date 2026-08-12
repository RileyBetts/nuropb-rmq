# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Single source of truth for orders.get_status params and result."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GetStatusParams(BaseModel):
    """Arguments the LLM must supply to call ``orders.get_status``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: str = Field(
        ...,
        min_length=1,
        description="Customer order id, e.g. ORD-1001",
    )


class OrderStatus(BaseModel):
    """Result shape returned by ``orders.get_status``."""

    model_config = ConfigDict(extra="forbid", strict=True)

    order_id: str
    status: Literal["processing", "shipped", "delivered", "cancelled"]
    carrier: str | None = None
    eta: str | None = None
    tracking: str | None = None
