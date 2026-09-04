/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ

open Std.Async
open NuropbRMQ

def main : IO Unit := Examples.Common.runAsync do
  let c ← connect (← liftM Examples.Common.cfg)
  let _ ← openChannel c 1
  let q ← queueDeclare c 1 "nr.ex.hello" (durable := true)
  let _ ← basicConsume c 1 q
  let msg ← receive c 15000
  basicAck c 1 msg.deliveryTag
  let text := (String.fromUTF8? msg.body).getD ""
  liftM (IO.println s!"received '{text}'")
  close c
