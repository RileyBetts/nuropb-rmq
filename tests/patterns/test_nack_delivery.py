# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""RpcServer NackDelivery settles with basic.nack (no JSON-RPC reply)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from nuropb_rmq.api import NackDelivery
from nuropb_rmq.patterns.envelope import encode_request
from nuropb_rmq.patterns.rpc import RpcServer
from nuropb_rmq.transport.connection import IncomingMessage


@pytest.mark.asyncio
async def test_nack_delivery_settles_without_reply() -> None:
    conn = MagicMock()
    conn.basic_nack = AsyncMock()
    conn.basic_publish = AsyncMock()
    conn.basic_ack = AsyncMock()

    def handler(_method: str, _params: object) -> object:
        raise NackDelivery(requeue=False)

    srv = RpcServer(queue="q", handler=handler, conn=conn, declare_queue=False)
    msg = IncomingMessage(
        delivery_tag=7,
        exchange="",
        routing_key="q",
        body=encode_request("orders.ping", {}, "id-1"),
        properties={"reply_to": "nr.reply.x", "correlation_id": "id-1"},
        redelivered=False,
        consumer_tag="c",
    )
    await srv._handle(msg)
    conn.basic_nack.assert_awaited_once_with(1, 7, requeue=False)
    conn.basic_publish.assert_not_called()
    conn.basic_ack.assert_not_called()
