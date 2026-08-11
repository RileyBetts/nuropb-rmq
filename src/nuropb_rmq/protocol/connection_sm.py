"""Connection state machine (SpeC++ invariants 1–5, 7)."""

from __future__ import annotations

from enum import Enum, auto


class ConnState(Enum):
    INIT = auto()
    TCP_CONNECTED = auto()
    TLS_HANDSHAKING = auto()
    TLS_VERIFIED = auto()
    START = auto()
    START_OK = auto()
    TUNE = auto()
    TUNE_OK = auto()
    OPEN = auto()
    OPEN_OK = auto()
    CLOSING = auto()
    CLOSED = auto()
    ERROR = auto()


class ProtocolError(RuntimeError):
    """Illegal AMQP state transition — connection must tear down."""


_TERMINAL = {ConnState.CLOSED, ConnState.ERROR}


class ConnectionStateMachine:
    """Fail-closed connection SM: rejected transitions raise and move to ERROR."""

    def __init__(self) -> None:
        self.state = ConnState.INIT
        self.heartbeat: int = 60  # single profile-configured value (invariant 7)

    @property
    def is_open(self) -> bool:
        return self.state == ConnState.OPEN_OK

    def _goto(self, new: ConnState) -> None:
        self.state = new

    def reject(self, reason: str) -> None:
        self.state = ConnState.ERROR
        raise ProtocolError(reason)

    def on_tcp_connected(self, *, tls: bool) -> None:
        if self.state != ConnState.INIT:
            self.reject(f"tcp connect in state {self.state}")
        self._goto(ConnState.TLS_HANDSHAKING if tls else ConnState.TCP_CONNECTED)

    def on_tls_verified(self) -> None:
        if self.state != ConnState.TLS_HANDSHAKING:
            self.reject(f"tls verified in state {self.state}")
        self._goto(ConnState.TLS_VERIFIED)

    def allow_amqp_header(self) -> None:
        """Invariant 2: AMQP negotiation only after TCP or verified TLS."""
        if self.state == ConnState.TLS_HANDSHAKING:
            self.reject("AMQP header before TLS verified")
        if self.state not in {ConnState.TCP_CONNECTED, ConnState.TLS_VERIFIED}:
            self.reject(f"AMQP header in state {self.state}")

    def on_connection_start(self) -> None:
        if self.state not in {ConnState.TCP_CONNECTED, ConnState.TLS_VERIFIED}:
            self.reject(f"connection.start in state {self.state}")
        self._goto(ConnState.START)

    def on_connection_start_ok_sent(self) -> None:
        if self.state != ConnState.START:
            self.reject(f"connection.start-ok in state {self.state}")
        self._goto(ConnState.START_OK)

    def on_connection_tune(self) -> None:
        if self.state != ConnState.START_OK:
            self.reject(f"connection.tune in state {self.state}")
        self._goto(ConnState.TUNE)

    def on_connection_tune_ok_sent(self, *, heartbeat: int) -> None:
        if self.state != ConnState.TUNE:
            self.reject(f"connection.tune-ok in state {self.state}")
        if heartbeat <= 0 or heartbeat > 60:
            self.reject(f"invalid heartbeat {heartbeat}")
        self.heartbeat = heartbeat
        self._goto(ConnState.TUNE_OK)

    def on_connection_open_sent(self) -> None:
        if self.state != ConnState.TUNE_OK:
            self.reject(f"connection.open in state {self.state}")
        self._goto(ConnState.OPEN)

    def on_connection_open_ok(self) -> None:
        if self.state != ConnState.OPEN:
            self.reject(f"connection.open-ok in state {self.state}")
        self._goto(ConnState.OPEN_OK)

    def begin_close(self) -> None:
        if self.state in _TERMINAL:
            self.reject(f"close in terminal state {self.state}")
        self._goto(ConnState.CLOSING)

    def on_close_ok(self) -> None:
        self._goto(ConnState.CLOSED)

    def assert_can_send_connection_method(self, method_id: int) -> None:
        """Invariant 1: only legal connection methods for current state."""
        from nuropb_rmq.protocol import methods as m

        legal = {
            m.CONNECTION_START_OK: ConnState.START,
            m.CONNECTION_TUNE_OK: ConnState.TUNE,
            m.CONNECTION_OPEN: ConnState.TUNE_OK,
            m.CONNECTION_CLOSE: {
                ConnState.OPEN_OK,
                ConnState.OPEN,
                ConnState.TUNE_OK,
                ConnState.TUNE,
                ConnState.START_OK,
                ConnState.START,
            },
            m.CONNECTION_CLOSE_OK: ConnState.CLOSING,
        }
        allowed = legal.get(method_id)
        if allowed is None:
            self.reject(f"unknown connection method {method_id}")
        if isinstance(allowed, set):
            if self.state not in allowed:
                self.reject(f"connection method {method_id} illegal in {self.state}")
        elif self.state != allowed:
            self.reject(f"connection method {method_id} illegal in {self.state}")
