import NuropbRmq.Session.DeadLetterTimeout
import NuropbRmq.Session.Reconnect
import NuropbRmq.Session.Invariants

/-!
Phase 2 invariants: DLQ/TTL exclusivity, first-wins across arrivals,
reconnect epoch clears outstanding and brackets reply queue.
-/

namespace NuropbRmq.Session

/-! ### Dead-letter / TTL exclusivity -/

theorem exclusiveFate_acked_ttl :
    exclusiveFate .ackedByService .ttlExpired = false := by native_decide

theorem exclusiveFate_ttl_acked :
    exclusiveFate .ttlExpired .ackedByService = false := by native_decide

theorem exclusiveFate_inQueue_ok :
    exclusiveFate .inQueue .ttlExpired = true := by native_decide

theorem expire_after_ack_is_none :
    expireTtl { fate := .ackedByService } = none := by
  simp [expireTtl]

theorem ack_after_expire_is_none :
    ackService { fate := .ttlExpired } = none := by
  simp [ackService]

theorem synthesize_requires_ttl (s : RequestState)
    (h : s.fate ≠ .ttlExpired) :
    synthesizeTimeout s = none := by
  simp [synthesizeTimeout]
  intro hf
  exact (h hf).elim

theorem terminal_acked :
    terminalOf { fate := .ackedByService } = .ackedWithResponse := by
  simp [terminalOf]

theorem terminal_timeout :
    terminalOf { fate := .ttlExpired, timeoutSynthesized := true } =
      .dlqTimeoutSynthesized := by
  simp [terminalOf]

/-! ### First-reply-wins (Correlation Phase 1b) -/

theorem first_wins_then_late (s : State) (id : CorrId)
    (_hin : contains s.pending id = true) :
    tryResolve { s with pending := removeId s.pending id } id =
      .lateDiscard { s with pending := removeId s.pending id } :=
  second_resolve_is_late s id

/-! ### Reconnect epoch -/

theorem disconnect_clears (s : ReconnectState) :
    (onDisconnect s).pendingCount = 0 ∧ (onDisconnect s).replyOpen = false := by
  simp [onDisconnect]

theorem reconnect_bumps_epoch (s : ReconnectState) :
    (onReconnect s).epoch = s.epoch + 1 ∧
      (onReconnect s).pendingCount = 0 ∧
      (onReconnect s).replyOpen = true := by
  simp [onReconnect]

theorem reconnect_wellFormed (s : ReconnectState) :
    wellFormedEpoch (onReconnect s) = true := by
  simp [onReconnect, wellFormedEpoch]

theorem register_requires_open (s : ReconnectState)
    (h : s.replyOpen = false) :
    register s = none := by
  simp [register, h]

theorem disconnect_then_reconnect_wellFormed (s : ReconnectState) :
    wellFormedEpoch (onReconnect (onDisconnect s)) = true := by
  simp [onDisconnect, onReconnect, wellFormedEpoch]

end NuropbRmq.Session
