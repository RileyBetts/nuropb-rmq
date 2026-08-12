/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Phase 2: reconnect epoch — old reply queue ends; outstanding cleared;
new reply queue brackets a fresh correlation table.
-/

namespace NuropbRmq.Session

structure ReconnectState where
  epoch : Nat := 0
  replyOpen : Bool := false
  pendingCount : Nat := 0
  deriving Repr

def wellFormedEpoch (s : ReconnectState) : Bool :=
  !(decide (s.pendingCount ≠ 0)) || s.replyOpen

/-- Fail-fast disconnect: clear outstanding, close reply queue. -/
def onDisconnect (s : ReconnectState) : ReconnectState :=
  { s with replyOpen := false, pendingCount := 0 }

/-- New connection epoch with empty table and open reply queue. -/
def onReconnect (s : ReconnectState) : ReconnectState :=
  { epoch := s.epoch + 1, replyOpen := true, pendingCount := 0 }

def register (s : ReconnectState) : Option ReconnectState :=
  if !s.replyOpen then none
  else some { s with pendingCount := s.pendingCount + 1 }

end NuropbRmq.Session
