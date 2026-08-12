/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Channel-layer states aligned with SpeC++ `ChanState` / Python `channel_sm.ChanState`.
-/

namespace NuropbRmq.Protocol

inductive ChanState where
  | closed
  | opening
  | open
  | closing
  | error
  deriving DecidableEq, Repr, Inhabited

def ChanState.isOpen : ChanState → Bool
  | .open => true
  | _ => false

/-- Channel ops (declare/publish/consume/ack) require OPEN. -/
def ChanState.allowsOps : ChanState → Bool
  | .open => true
  | _ => false

end NuropbRmq.Protocol
