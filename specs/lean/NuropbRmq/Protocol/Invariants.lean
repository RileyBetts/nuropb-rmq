/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.ConnectionSM
import NuropbRmq.Protocol.FrameDecode

/-!
Protocol invariants 1–7 proved against the Lean connection/channel model.
-/

namespace NuropbRmq.Protocol

/-! ### Invariant 4: rejected transition → ERROR (never silent stay) -/

theorem reject_implies_error (s : State) (e : Event)
    (h : tryStep s e = none) :
    (step s e).conn = .error ∧ (step s e).chan = .error := by
  simp [step, h]

theorem reject_event_tears_down (s : State) :
    (step s .reject).conn = .error := by
  simp [step, tryStep]

/-! ### Invariant 1: legalSend gates connection sends -/

theorem legalSend_startOk : legalSend .startOk .start = true := rfl
theorem legalSend_tuneOk : legalSend .tuneOk .tune = true := rfl
theorem legalSend_open : legalSend .open .tuneOk = true := rfl
theorem legalSend_closeOk : legalSend .closeOk .closing = true := rfl
theorem legalSend_updateSecret : legalSend .updateSecret .openOk = true := rfl
theorem legalSend_updateSecret_not_start :
    legalSend .updateSecret .start = false := rfl

theorem legalSend_startOk_only_start (c : ConnState)
    (h : legalSend .startOk c = true) : c = .start := by
  cases c <;> simp [legalSend] at h ⊢

theorem tryStep_startOk_requires_start (s : State) (s' : State)
    (h : tryStep s .startOk = some s') : s.conn = .start := by
  simp [tryStep] at h
  exact h.1

theorem tryStep_startOk_requires_legal (s : State) (s' : State)
    (h : tryStep s .startOk = some s') :
    legalSend .startOk s.conn = true := by
  simp [tryStep] at h
  exact h.2.2.1

/-! ### Invariant 2: AMQP requires verified TLS when TLS configured -/

theorem amqpHeader_rejects_during_tls_handshake (s : State)
    (h : s.conn = .tlsHandshaking) :
    tryStep s .amqpHeader = none := by
  simp [tryStep, h]

theorem connStart_requires_verified_tls (s : State) (s' : State)
    (hcfg : s.config.tlsConfigured = true)
    (h : tryStep s .connStart = some s') :
    s.tlsVerifiedFlag = true := by
  simp [tryStep] at h
  exact h.2.1 hcfg

/-! ### Invariant 3: SASL/startOk requires verified TLS when TLS configured -/

theorem startOk_requires_verified_tls (s : State) (s' : State)
    (hcfg : s.config.tlsConfigured = true)
    (h : tryStep s .startOk = some s') :
    s.tlsVerifiedFlag = true := by
  simp [tryStep] at h
  exact h.2.1 hcfg

/-! ### Invariant 5: close is reachable from every state -/

theorem close_reachable_all (c : ConnState) : c.closeReachable = true := by
  cases c <;> rfl

theorem beginClose_ok_from_openOk :
    (tryStep { conn := .openOk } .beginClose).isSome = true := by
  native_decide

/-! ### Invariant 7: single heartbeat policy / validated range -/

private theorem tuneOk_success_shape (s : State) (hb : Nat) (s' : State)
    (h : tryStep s (.tuneOk hb) = some s') :
    s.conn = .tune ∧ (hb ≠ 0 ∧ hb ≤ 60) ∧
      legalSend .tuneOk s.conn = true ∧
      { s with conn := .tuneOk, heartbeat := hb } = s' := by
  simp [tryStep] at h
  exact h

theorem tuneOk_heartbeat_bounds (s : State) (hb : Nat) (s' : State)
    (h : tryStep s (.tuneOk hb) = some s') :
    s'.heartbeat = hb ∧ hb ≠ 0 ∧ hb ≤ 60 := by
  obtain ⟨_, ⟨hb0, hb60⟩, _, hs'⟩ := tuneOk_success_shape s hb s' h
  subst hs'
  exact ⟨rfl, hb0, hb60⟩

theorem step_preserves_heartbeat_exists (s : State) (e : Event) :
    ∃ hb : Nat, (step s e).heartbeat = hb :=
  ⟨(step s e).heartbeat, rfl⟩

/-! ### Invariant 6: frame decode bounds -/

theorem inv6_decodeAccepted_implies_bounds
    (size depth frameMax maxTableDepth : Nat)
    (h : decodeAccepted size depth frameMax maxTableDepth = true) :
    size + 8 ≤ frameMax ∧ depth ≤ maxTableDepth :=
  decodeAccepted_implies_bounds size depth frameMax maxTableDepth h

/-! ### Happy-path witness (spec admits a model) -/

def plainOpenOk : State :=
  let s0 : State := {}
  let s1 := step s0 (.tcpConnected false)
  let s2 := step s1 .amqpHeader
  let s3 := step s2 .connStart
  let s4 := step s3 .startOk
  let s5 := step s4 .tune
  let s6 := step s5 (.tuneOk 30)
  let s7 := step s6 .open
  step s7 .openOk

theorem plainOpenOk_is_open : plainOpenOk.conn = .openOk := by native_decide
theorem plainOpenOk_heartbeat : plainOpenOk.heartbeat = 30 := by native_decide

/-- TLS path: handshake must complete before AMQP start. -/
def tlsOpenOk : State :=
  let s0 : State := {}
  let s1 := step s0 (.tcpConnected true)
  let s2 := step s1 .tlsVerified
  let s3 := step s2 .amqpHeader
  let s4 := step s3 .connStart
  let s5 := step s4 .startOk
  let s6 := step s5 .tune
  let s7 := step s6 (.tuneOk 60)
  let s8 := step s7 .open
  step s8 .openOk

theorem tlsOpenOk_is_open : tlsOpenOk.conn = .openOk := by native_decide
theorem tlsOpenOk_verified : tlsOpenOk.tlsVerifiedFlag = true := by native_decide

/-- Skipping TLS verify fails closed. -/
theorem tls_skip_verify_errors :
    (step (step {} (.tcpConnected true)) .amqpHeader).conn = .error := by
  native_decide

theorem blocked_refuses_publish :
    publishAllowed { conn := .openOk, blocked := true } = false := rfl

theorem unblocked_allows_publish :
    publishAllowed { conn := .openOk, blocked := false } = true := by native_decide

theorem two_missed_heartbeats_lost :
    (step (step { conn := .openOk } (.heartbeatPeer false)) (.heartbeatPeer false)).conn =
      .error := by
  native_decide

theorem heard_heartbeat_resets :
    ((tryStep { conn := .openOk, missedHeartbeats := 1 } (.heartbeatPeer true)).map
      (·.missedHeartbeats)) = some 0 := by
  native_decide

/-! ### Channel SM (ops require OPEN) -/

theorem allowsOps_iff_open (c : ChanState) :
    c.allowsOps = true ↔ c = .open := by
  cases c <;> simp [ChanState.allowsOps]

theorem chanOpen_requires_conn_openOk (s s' : State)
    (h : tryStep s .chanOpen = some s') : s.conn = .openOk := by
  simp [tryStep] at h
  exact h.1

theorem chanOpen_requires_closed (s s' : State)
    (h : tryStep s .chanOpen = some s') : s.chan = .closed := by
  simp [tryStep] at h
  exact h.2.1

theorem chanOpenOk_opens (s s' : State)
    (h : tryStep s .chanOpenOk = some s') : s'.chan = .open := by
  simp [tryStep] at h
  obtain ⟨_, hs'⟩ := h
  subst hs'
  rfl

theorem chanOp_requires_allowsOps (s s' : State)
    (h : tryStep s .chanOp = some s') : s.chan.allowsOps = true := by
  simp [tryStep] at h
  exact h.1

theorem chanOp_refused_when_closed (s : State) (h : s.chan = .closed) :
    tryStep s .chanOp = none := by
  simp [tryStep, h, ChanState.allowsOps]

/-! ### Reachable (inductive closure of `step`) -/

theorem reachable_init : Reachable {} := .init

theorem reachable_closed_under_step (s : State) (e : Event)
    (h : Reachable s) : Reachable (step s e) :=
  .step s e h

private theorem reachable_chain8 (e1 e2 e3 e4 e5 e6 e7 e8 : Event) :
    Reachable (step (step (step (step (step (step (step (step {}
      e1) e2) e3) e4) e5) e6) e7) e8) :=
  .step _ e8 <| .step _ e7 <| .step _ e6 <| .step _ e5 <|
    .step _ e4 <| .step _ e3 <| .step _ e2 <| .step _ e1 <| .init

private theorem reachable_chain9 (e1 e2 e3 e4 e5 e6 e7 e8 e9 : Event) :
    Reachable (step (step (step (step (step (step (step (step (step {}
      e1) e2) e3) e4) e5) e6) e7) e8) e9) :=
  .step _ e9 <| reachable_chain8 e1 e2 e3 e4 e5 e6 e7 e8

theorem reachable_plainOpenOk : Reachable plainOpenOk := by
  unfold plainOpenOk
  exact reachable_chain8 (.tcpConnected false) .amqpHeader .connStart .startOk
    .tune (.tuneOk 30) .open .openOk

theorem reachable_tlsOpenOk : Reachable tlsOpenOk := by
  unfold tlsOpenOk
  exact reachable_chain9 (.tcpConnected true) .tlsVerified .amqpHeader .connStart
    .startOk .tune (.tuneOk 60) .open .openOk

end NuropbRmq.Protocol
