# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Correlation table: id -> Future with first-reply-wins semantics."""

from __future__ import annotations

import asyncio
from typing import Any

from nuropb_rmq.session.ids import IdCollisionError, generate_id, validate_id


class CorrelationTable:
    """Outstanding request id → Future. First resolve wins; later discarded."""

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[Any]] = {}

    def __contains__(self, request_id: str) -> bool:
        return request_id in self._pending

    def __len__(self) -> int:
        return len(self._pending)

    @property
    def outstanding(self) -> frozenset[str]:
        return frozenset(self._pending)

    def register(self, request_id: str | None = None) -> tuple[str, asyncio.Future[Any]]:
        if request_id is None:
            request_id = generate_id()
            while request_id in self._pending:
                request_id = generate_id()
        else:
            request_id = validate_id(request_id)
            if request_id in self._pending:
                raise IdCollisionError(f"id collides with outstanding request: {request_id}")
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = fut
        return request_id, fut

    def resolve(self, request_id: str, value: Any) -> bool:
        """First reply wins. Returns True if this reply resolved a pending future."""
        fut = self._pending.pop(request_id, None)
        if fut is None:
            return False  # late / unknown — discard silently
        if not fut.done():
            fut.set_result(value)
        return True

    def fail(self, request_id: str, exc: BaseException) -> bool:
        fut = self._pending.pop(request_id, None)
        if fut is None:
            return False
        if not fut.done():
            fut.set_exception(exc)
        return True

    def discard_all(self, exc: BaseException | None = None) -> None:
        err = exc or ConnectionError("session closed")
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(err)
        self._pending.clear()
