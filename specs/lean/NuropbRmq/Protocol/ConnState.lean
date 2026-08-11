/-!
Connection-layer states aligned with SpeC++ `ConnState` / Python `connection_sm.ConnState`.
-/

namespace NuropbRmq.Protocol

inductive ConnState where
  | init
  | tcpConnected
  | tlsHandshaking
  | tlsVerified
  | start
  | startOk
  | tune
  | tuneOk
  | open
  | openOk
  | closing
  | closed
  | error
  deriving DecidableEq, Repr, Inhabited

/-- Terminal connection states. -/
def ConnState.isTerminal : ConnState → Bool
  | .closed | .error => true
  | _ => false

/-- Non-terminal states can still initiate close (invariant 5). -/
def ConnState.closeReachable : ConnState → Bool
  | .closed | .error => true  -- already terminal
  | .init | .tcpConnected | .tlsHandshaking | .tlsVerified
  | .start | .startOk | .tune | .tuneOk | .open | .openOk | .closing => true

inductive TlsState where
  | off
  | handshaking
  | verified
  | failed
  deriving DecidableEq, Repr, Inhabited

/-- Outbound connection methods gated by `legalSend` (invariant 1). -/
inductive ConnMethod where
  | startOk
  | tuneOk
  | open
  | close
  | closeOk
  deriving DecidableEq, Repr

end NuropbRmq.Protocol
