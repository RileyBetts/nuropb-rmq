/-!
Config queue/delivery profile consistency.

Mirrors SpeC++ `specs/specpp/Config/queue_profile*.smt2` and Python
`nuropb_rmq.config.queue_profile.QueueProfile`: durable queues require
`delivery_mode = 2`; non-durable require `delivery_mode = 1`.
-/

namespace NuropbRmq.Config

/-- AMQP delivery_mode: 1 = non-persistent, 2 = persistent. -/
abbrev DeliveryMode := Nat

structure QueueProfile where
  durable : Bool
  deliveryMode : DeliveryMode
  deriving Repr

/-- SpeC++ `profile_ok` / Python `__post_init__` durable↔persistence coupling. -/
def consistent (p : QueueProfile) : Bool :=
  (p.deliveryMode = 1 || p.deliveryMode = 2) &&
    (if p.durable then p.deliveryMode = 2 else p.deliveryMode = 1)

/-- Named default: durable-at-least-once work queue. -/
def durableAtLeastOnce : QueueProfile :=
  { durable := true, deliveryMode := 2 }

/-- Named transient-fast-path. -/
def transientFastPath : QueueProfile :=
  { durable := false, deliveryMode := 1 }

/-- Illegal: durable + non-persistent (Python raises). -/
def badDurableNonPersistent : QueueProfile :=
  { durable := true, deliveryMode := 1 }

/-- Illegal: non-durable + persistent (Python raises). -/
def badTransientPersistent : QueueProfile :=
  { durable := false, deliveryMode := 2 }

end NuropbRmq.Config
