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
