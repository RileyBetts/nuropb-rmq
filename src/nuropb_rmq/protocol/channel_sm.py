# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Channel state machine (fail-closed)."""

from __future__ import annotations

from enum import Enum, auto

from nuropb_rmq.protocol.connection_sm import ProtocolError


class ChanState(Enum):
    CLOSED = auto()
    OPENING = auto()
    OPEN = auto()
    CLOSING = auto()
    ERROR = auto()


class ChannelStateMachine:
    def __init__(self, channel_id: int) -> None:
        self.channel_id = channel_id
        self.state = ChanState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == ChanState.OPEN

    def reject(self, reason: str) -> None:
        self.state = ChanState.ERROR
        raise ProtocolError(reason)

    def on_open_sent(self) -> None:
        if self.state != ChanState.CLOSED:
            self.reject(f"channel.open in state {self.state}")
        self.state = ChanState.OPENING

    def on_open_ok(self) -> None:
        if self.state != ChanState.OPENING:
            self.reject(f"channel.open-ok in state {self.state}")
        self.state = ChanState.OPEN

    def begin_close(self) -> None:
        if self.state != ChanState.OPEN:
            self.reject(f"channel.close in state {self.state}")
        self.state = ChanState.CLOSING

    def on_close_ok(self) -> None:
        self.state = ChanState.CLOSED

    def assert_open_for_ops(self) -> None:
        if self.state != ChanState.OPEN:
            self.reject(f"channel op requires OPEN, got {self.state}")
