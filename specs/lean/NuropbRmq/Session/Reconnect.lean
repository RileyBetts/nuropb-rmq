/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Phase 2: reconnect epoch — fail-fast clears outstanding; park keeps pending
across the reply-queue gap; new reply queue on reconnect.
-/

namespace NuropbRmq.Session

structure ReconnectState where
  epoch : Nat := 0
  replyOpen : Bool := false
  pendingCount : Nat := 0
  deriving Repr

/-- Fail-fast: pending nonempty only while reply queue is open. -/
def wellFormedFailFast (s : ReconnectState) : Bool :=
  !(decide (s.pendingCount ≠ 0)) || s.replyOpen

/-- Park gap: pending may be nonzero while replyOpen is false. -/
def wellFormedPark (_s : ReconnectState) : Bool := true

def wellFormedEpoch (s : ReconnectState) : Bool := wellFormedFailFast s

/-- Fail-fast disconnect: clear outstanding, close reply queue. -/
def onDisconnect (s : ReconnectState) : ReconnectState :=
  { s with replyOpen := false, pendingCount := 0 }

/-- Park disconnect: keep outstanding futures; reply queue gone. -/
def onDisconnectPark (s : ReconnectState) : ReconnectState :=
  { s with replyOpen := false }

/-- New connection epoch. Park keeps pendingCount; fail-fast already cleared it. -/
def onReconnect (s : ReconnectState) : ReconnectState :=
  { epoch := s.epoch + 1, replyOpen := true, pendingCount := s.pendingCount }

def register (s : ReconnectState) : Option ReconnectState :=
  if !s.replyOpen then none
  else some { s with pendingCount := s.pendingCount + 1 }

/-- At most one client-visible terminal per id (first reply or CONNECTION_LOST). -/
inductive ClientTerminal where
  | none
  | reply
  | connectionLost
  deriving DecidableEq, Repr

def completeOnce (already : ClientTerminal) (next : ClientTerminal) : ClientTerminal :=
  if already != .none then already else next

theorem completeOnce_idempotent (t : ClientTerminal) :
    completeOnce t t = t := by
  cases t <;> rfl

theorem completeOnce_first_wins (a b : ClientTerminal) (h : a ≠ .none) :
    completeOnce a b = a := by
  cases a <;> simp [completeOnce] at h ⊢

end NuropbRmq.Session
