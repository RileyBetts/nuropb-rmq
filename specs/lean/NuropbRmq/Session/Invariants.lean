import NuropbRmq.Session.Correlation

/-!
Session Phase 1b invariants: id format, dual-accessor, collision reject,
first-reply-wins, reply-queue lifetime brackets correlation table.
-/

namespace NuropbRmq.Session

/-! ### Id format -/

theorem validIdLen_bounds (id : CorrId) (h : validIdLen id = true) :
    1 ≤ id ∧ id ≤ 255 := by
  simpa [validIdLen] using h

theorem register_rejects_invalid (s : State) (id : CorrId)
    (hopen : s.replyOpen = true) (hbad : validIdLen id = false) :
    tryRegister s id = .invalidId := by
  simp [tryRegister, hopen, hbad]

/-! ### Dual-accessor consistency -/

theorem dual_accessor_refl (id : CorrId) : dualAccessorOk id id := rfl

theorem dual_accessor_eq (a b : CorrId) (h : dualAccessorOk a b) : a = b := h

/-! ### Collision reject -/

theorem register_collision (s : State) (id : CorrId)
    (hopen : s.replyOpen = true)
    (hvalid : validIdLen id = true)
    (hin : contains s.pending id = true) :
    tryRegister s id = .collision := by
  simp [tryRegister, hopen, hvalid, hin]

theorem register_ok_fresh (s : State) (id : CorrId)
    (hopen : s.replyOpen = true)
    (hvalid : validIdLen id = true)
    (hfresh : contains s.pending id = false) :
    tryRegister s id = .ok { s with pending := id :: s.pending } := by
  simp [tryRegister, hopen, hvalid, hfresh]

/-! ### First-reply-wins / late discard -/

theorem resolve_first_wins (s : State) (id : CorrId)
    (hin : contains s.pending id = true) :
    tryResolve s id = .firstWin { s with pending := removeId s.pending id } := by
  simp [tryResolve, hin]

theorem resolve_removes_id (xs : List CorrId) (id : CorrId) :
    contains (removeId xs id) id = false := by
  simp [contains, removeId]

theorem resolve_late_discard (s : State) (id : CorrId)
    (hmiss : contains s.pending id = false) :
    tryResolve s id = .lateDiscard s := by
  simp [tryResolve, hmiss]

theorem second_resolve_is_late (s : State) (id : CorrId) :
    tryResolve { s with pending := removeId s.pending id } id =
      .lateDiscard { s with pending := removeId s.pending id } := by
  have hgone : contains (removeId s.pending id) id = false :=
    resolve_removes_id s.pending id
  simpa [tryResolve] using hgone

/-! ### Reply-queue lifetime brackets correlation table -/

theorem register_requires_reply_open (s : State) (id : CorrId)
    (hclosed : s.replyOpen = false) :
    tryRegister s id = .replyClosed := by
  simp [tryRegister, hclosed]

theorem close_clears_pending (s : State) :
    (closeReply s).pending = [] ∧ (closeReply s).replyOpen = false := by
  simp [closeReply]

theorem close_wellFormed (s : State) : wellFormed (closeReply s) = true := by
  simp [closeReply, wellFormed]

theorem open_empty_wellFormed : wellFormed (openReply {}) = true := by
  native_decide

theorem register_keeps_wellFormed (id : CorrId)
    (hvalid : validIdLen id = true) :
    wellFormed { pending := [id], replyOpen := true } = true ∧
      tryRegister (openReply {}) id =
        .ok { pending := [id], replyOpen := true } := by
  constructor
  · simp [wellFormed]
  · simp [tryRegister, openReply, contains, hvalid]

theorem empty_pending_wellFormed (r : Bool) :
    wellFormed { pending := [], replyOpen := r } = true := by
  cases r <;> native_decide

end NuropbRmq.Session
