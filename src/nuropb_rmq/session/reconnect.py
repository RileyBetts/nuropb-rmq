# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Reconnect coordination (fail-fast outstanding RPCs; new Session epoch).

v1 policy: on disconnect, outstanding requests fail with CONNECTION_LOST.
Reconnect opens a new TCP/AMQP connection and exclusive reply queue.
MeshService / RpcServer consumers are rebound/restarted by the caller —
no silent in-flight retry (avoids multi-path outcomes).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from nuropb_rmq.session.session import Session


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Fail-fast reconnect policy (park-and-retry deferred)."""

    max_attempts: int = 5
    initial_backoff_s: float = 0.05
    max_backoff_s: float = 2.0
    # v1: always fail outstanding on disconnect (field documents the decision)
    fail_outstanding: bool = True

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if not self.fail_outstanding:
            raise ValueError("park-and-retry is out of scope for v1; fail_outstanding must be True")


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
