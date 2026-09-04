/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ

def main : IO Unit := do
  let c ← NuropbRMQ.connect (← Examples.Common.cfg)
  let _ ← NuropbRMQ.openChannel c 1
  let q ← NuropbRMQ.queueDeclare c 1 "nr.ex.hello" (durable := true)
  let _ ← NuropbRMQ.basicConsume c 1 q
  let msg ← NuropbRMQ.receive c 15000
  NuropbRMQ.basicAck c 1 msg.deliveryTag
  let text := (String.fromUTF8? msg.body).getD ""
  IO.println s!"received '{text}'"
  NuropbRMQ.close c
