/-!
Session correlation model (Lean Phase 1b).

Mirrors SpeC++ Session sorts and Python
`nuropb_rmq.session.{ids,correlation,session}`.
-/

namespace NuropbRmq.Session

/-- Abstract correlation id as octet length in `1..255` (AMQP shortstr bound). -/
abbrev CorrId := Nat

/-- Id format: 1..255 octets (charset abstracted as a Bool flag at the boundary). -/
def validIdLen (id : CorrId) : Bool :=
  decide (1 ≤ id ∧ id ≤ 255)

/-- Dual-accessor consistency: AMQP `correlation_id` and JSON-RPC `id` are equal. -/
def dualAccessorOk (amqpId jsonId : CorrId) : Prop :=
  amqpId = jsonId

structure State where
  /-- Outstanding request ids in the correlation table. -/
  pending : List CorrId := []
  /-- Exclusive reply queue declared and consuming. -/
  replyOpen : Bool := false
  deriving Repr

def contains (xs : List CorrId) (id : CorrId) : Bool :=
  xs.elem id

def removeId (xs : List CorrId) (id : CorrId) : List CorrId :=
  xs.filter (fun x => !decide (x = id))

inductive RegResult where
  | ok (s : State)
  | invalidId
  | collision
  | replyClosed
  deriving Repr

inductive ResResult where
  /-- First reply wins; id removed from pending. -/
  | firstWin (s : State)
  /-- Late / unknown — discarded; state unchanged. -/
  | lateDiscard (s : State)
  deriving Repr

/-- Open exclusive reply queue; brackets correlation-table lifetime. -/
def openReply (_s : State) : State :=
  { pending := [], replyOpen := true }

/-- Close reply queue and clear outstanding futures (Python `discard_all`). -/
def closeReply (_s : State) : State :=
  { pending := [], replyOpen := false }

/-- Register a caller- or library-supplied id. Collision / invalid → reject. -/
def tryRegister (s : State) (id : CorrId) : RegResult :=
  if !s.replyOpen then .replyClosed
  else if !(validIdLen id) then .invalidId
  else if contains s.pending id then .collision
  else .ok { s with pending := id :: s.pending }

/-- Resolve a reply: first wins, later discarded. -/
def tryResolve (s : State) (id : CorrId) : ResResult :=
  if contains s.pending id then
    .firstWin { s with pending := removeId s.pending id }
  else
    .lateDiscard s

/-- Well-formedness: pending nonempty only while reply queue is open. -/
def wellFormed (s : State) : Bool :=
  !(decide (s.pending ≠ [])) || s.replyOpen

end NuropbRmq.Session
