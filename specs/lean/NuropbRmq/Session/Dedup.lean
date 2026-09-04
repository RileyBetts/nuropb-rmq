/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Process-local request-id dedup (server counterpart of client `completeOnce`).

Bounded seen list: `fresh` inserts and drops oldest when over cap;
`replay` leaves the list unchanged. Cap `0` is off (always fresh, no insert).
This is not exactly-once AMQP delivery and not clustered / HA dedup.
-/

namespace NuropbRmq.Session

abbrev RequestId := String

inductive DedupOutcome where
  | fresh
  | replay
  deriving DecidableEq, Repr

/-- Newest first. `take cap` after cons drops the oldest. -/
def tryDedup (seen : List RequestId) (cap : Nat) (id : RequestId) :
    DedupOutcome × List RequestId :=
  if id ∈ seen then
    (.replay, seen)
  else if cap = 0 then
    (.fresh, seen)
  else
    (.fresh, (id :: seen).take cap)

theorem tryDedup_replay (seen : List RequestId) (cap : Nat) (id : RequestId)
    (h : id ∈ seen) :
    tryDedup seen cap id = (.replay, seen) := by
  simp [tryDedup, h]

theorem tryDedup_fresh_off (seen : List RequestId) (id : RequestId)
    (h : id ∉ seen) :
    tryDedup seen 0 id = (.fresh, seen) := by
  simp [tryDedup, h]

theorem tryDedup_fresh (seen : List RequestId) (cap : Nat) (id : RequestId)
    (hmiss : id ∉ seen) (hcap : cap ≠ 0) :
    (tryDedup seen cap id).1 = .fresh := by
  simp [tryDedup, hmiss, hcap]

theorem tryDedup_second_replay (seen : List RequestId) (cap : Nat) (id : RequestId)
    (hmiss : id ∉ seen) (hcap : cap ≠ 0) :
    (tryDedup (tryDedup seen cap id).2 cap id).1 = .replay := by
  have hseen : (tryDedup seen cap id).2 = (id :: seen).take cap := by
    simp [tryDedup, hmiss, hcap]
  have hid : id ∈ (id :: seen).take cap := by
    cases cap with
    | zero => exact (hcap rfl).elim
    | succ n => simp
  rw [hseen]
  simp [tryDedup, hid]

theorem tryDedup_len_le_cap (seen : List RequestId) (cap : Nat) (id : RequestId)
    (hmiss : id ∉ seen) (hcap : cap ≠ 0) :
    (tryDedup seen cap id).2.length ≤ cap := by
  simp [tryDedup, hmiss, hcap]
  exact Nat.min_le_left _ _

theorem tryDedup_abc_fresh :
    (tryDedup [] 2 "abc").1 = .fresh := by
  native_decide

theorem tryDedup_abc_then_replay :
    (tryDedup (tryDedup [] 2 "abc").2 2 "abc").1 = .replay := by
  native_decide

theorem tryDedup_evicts_oldest :
    (tryDedup (tryDedup ["b", "a"] 2 "c").2 2 "a").1 = .fresh := by
  native_decide

end NuropbRmq.Session
