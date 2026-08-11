/-!
Phase 2: broker TTL / DLQ timeout terminal-state model.

Axiomatizes mutual exclusivity of successful service ack vs TTL
dead-letter + timeout synthesis (architecture Phase 2 invariant).
-/

namespace NuropbRmq.Session

inductive DeliveryFate where
  | inQueue
  | ackedByService
  | ttlExpired
  | timeoutSynthesized
  deriving DecidableEq, Repr

/-- Broker axiom: TTL expiry and successful service processing are exclusive. -/
def exclusiveFate (a b : DeliveryFate) : Bool :=
  !(a == .ackedByService && b == .ttlExpired) &&
  !(a == .ttlExpired && b == .ackedByService)

inductive Terminal where
  | none
  | ackedWithResponse
  | dlqTimeoutSynthesized
  | connectionLost
  deriving DecidableEq, Repr

structure RequestState where
  fate : DeliveryFate := .inQueue
  timeoutSynthesized : Bool := false
  replyOpen : Bool := true
  deriving Repr

def terminalOf (s : RequestState) : Terminal :=
  if s.fate == .ackedByService then .ackedWithResponse
  else if s.fate == .ttlExpired && s.timeoutSynthesized then .dlqTimeoutSynthesized
  else if !s.replyOpen then .connectionLost
  else .none

/-- Step: service acks while still in queue. -/
def ackService (s : RequestState) : Option RequestState :=
  if s.fate != .inQueue then none
  else some { s with fate := .ackedByService }

/-- Step: TTL expires while in queue (not already acked). -/
def expireTtl (s : RequestState) : Option RequestState :=
  if s.fate != .inQueue then none
  else some { s with fate := .ttlExpired }

/-- DLQ processor synthesizes timeout after TTL expiry. -/
def synthesizeTimeout (s : RequestState) : Option RequestState :=
  if s.fate != .ttlExpired then none
  else some { s with timeoutSynthesized := true }

end NuropbRmq.Session
