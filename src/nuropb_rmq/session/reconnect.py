# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Reconnect coordination: new Session epoch, optional park-and-retry.

Default policy parks in-flight RpcClient futures, opens a new exclusive reply
queue, and republishes with the same correlation id. Fail-fast
(``fail_outstanding=True``) still completes outstanding calls with
``CONNECTION_LOST``. MeshService / RpcServer consumers remain caller-owned.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from nuropb_rmq.session.session import Session


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Reconnect backoff and outstanding-RPC policy.

    ``fail_outstanding=False`` (default): park-and-retry — keep futures, republish
    after a new epoch. At-least-once on the server; handlers must be idempotent.

    ``fail_outstanding=True``: 0.5.x fail-fast — outstanding RPCs get
    ``CONNECTION_LOST`` immediately.
    """

    max_attempts: int = 5
    initial_backoff_s: float = 0.05
    max_backoff_s: float = 2.0
    fail_outstanding: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_backoff_s < 0 or self.max_backoff_s < 0:
            raise ValueError("backoff must be >= 0")


class ReconnectCoordinator:
    """Drive Session.reconnect with backoff until success or attempts exhausted."""

    def __init__(self, policy: ReconnectPolicy | None = None) -> None:
        self.policy = policy or ReconnectPolicy()

    async def reconnect(self, session: Session) -> Session:
        delay = self.policy.initial_backoff_s
        last_exc: BaseException | None = None
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                await session.reconnect()
                return session
            except Exception as exc:
                last_exc = exc
                if attempt >= self.policy.max_attempts:
                    break
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, self.policy.max_backoff_s)
        assert last_exc is not None
        raise last_exc
