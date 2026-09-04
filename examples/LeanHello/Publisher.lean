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
  let body := "hello-nuropb-rmq".toUTF8
  basicPublish c 1 body "" q { deliveryMode := some 2, contentType := some "text/plain" }
    (wantConfirm := true)
  liftM (IO.println "sent b'hello-nuropb-rmq'")
  close c
