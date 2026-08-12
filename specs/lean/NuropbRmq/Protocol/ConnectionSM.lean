/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.ConnState
import NuropbRmq.Protocol.ChanState

/-!
Connection/channel transition system aligned with SpeC++ and Python SMs.
-/

namespace NuropbRmq.Protocol

structure Config where
  tlsConfigured : Bool := false
  frameMax : Nat := 131072
  maxTableDepth : Nat := 32
  deriving Repr

structure State where
  conn : ConnState := .init
  chan : ChanState := .closed
  /-- True after a completed TLS handshake when TLS is configured. -/
  tlsVerifiedFlag : Bool := false
  /-- Single heartbeat policy field (invariant 7). -/
  heartbeat : Nat := 60
  config : Config := {}
  deriving Repr

inductive Event where
  | tcpConnected (useTls : Bool)
  | tlsVerified
  | amqpHeader
  | connStart
  | startOk
  | tune
  | tuneOk (hb : Nat)
  | open
  | openOk
  | beginClose
  | closeOk
  | reject
  | chanOpen
  | chanOpenOk
  | chanOp
  | chanBeginClose
  | chanCloseOk
  deriving Repr

/-- Invariant 1: outbound connection method legality. -/
def legalSend : ConnMethod → ConnState → Bool
  | .startOk, .start => true
  | .tuneOk, .tune => true
  | .open, .tuneOk => true
  | .close, .openOk => true
  | .close, .open => true
  | .close, .tuneOk => true
  | .close, .tune => true
  | .close, .startOk => true
  | .close, .start => true
  | .closeOk, .closing => true
  | _, _ => false

/-- Successful transition, or `none` if the event is illegal (must tear down). -/
def tryStep (s : State) : Event → Option State
  | .tcpConnected useTls =>
      if s.conn ≠ .init then none
      else if useTls then
        some { s with conn := .tlsHandshaking, config := { s.config with tlsConfigured := true } }
      else
        some { s with conn := .tcpConnected, config := { s.config with tlsConfigured := false } }
  | .tlsVerified =>
      if s.conn ≠ .tlsHandshaking then none
      else some { s with conn := .tlsVerified, tlsVerifiedFlag := true }
  | .amqpHeader =>
      -- Invariant 2: no AMQP negotiation during TLS handshake
      if s.conn = .tlsHandshaking then none
      else if s.conn = .tcpConnected ∨ s.conn = .tlsVerified then some s
      else none
  | .connStart =>
      if s.conn = .tcpConnected ∨ s.conn = .tlsVerified then
        -- Invariant 2: when TLS configured, must be verified
        if s.config.tlsConfigured && !s.tlsVerifiedFlag then none
        else some { s with conn := .start }
      else none
  | .startOk =>
      if s.conn ≠ .start then none
      -- Invariant 3: SASL/start-ok only trusted over verified TLS when TLS configured
      else if s.config.tlsConfigured && !s.tlsVerifiedFlag then none
      else if !legalSend .startOk s.conn then none
      else some { s with conn := .startOk }
  | .tune =>
      if s.conn ≠ .startOk then none
      else some { s with conn := .tune }
  | .tuneOk hb =>
      if s.conn ≠ .tune then none
      else if hb = 0 ∨ hb > 60 then none
      else if !legalSend .tuneOk s.conn then none
      else some { s with conn := .tuneOk, heartbeat := hb }
  | .open =>
      if s.conn ≠ .tuneOk then none
      else if !legalSend .open s.conn then none
      else some { s with conn := .open }
  | .openOk =>
      if s.conn ≠ .open then none
      else some { s with conn := .openOk }
  | .beginClose =>
      if s.conn.isTerminal then none
      else some { s with conn := .closing }
  | .closeOk =>
      some { s with conn := .closed }
  | .reject => none
  | .chanOpen =>
      if s.conn ≠ .openOk then none
      else if s.chan ≠ .closed then none
      else some { s with chan := .opening }
  | .chanOpenOk =>
      if s.chan ≠ .opening then none
      else some { s with chan := .open }
  | .chanOp =>
      if s.chan.allowsOps then some s else none
  | .chanBeginClose =>
      if s.chan ≠ .open then none
      else some { s with chan := .closing }
  | .chanCloseOk =>
      some { s with chan := .closed }

/-- Fail-closed step: illegal events tear down to ERROR (invariant 4). -/
def step (s : State) (e : Event) : State :=
  match tryStep s e with
  | some s' => s'
  | none => { s with conn := .error, chan := .error }

/-- Inductive reachable states from `init` via `step`. -/
inductive Reachable : State → Prop where
  | init : Reachable {}
  | step : ∀ s e, Reachable s → Reachable (step s e)

end NuropbRmq.Protocol
