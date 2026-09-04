/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ

def main : IO Unit := do
  let c ← NuropbRMQ.connect (← Examples.Common.cfg)
  let _ ← NuropbRMQ.openChannel c 1
  let q ← NuropbRMQ.queueDeclare c 1 Examples.Common.INTEROP_HELLO_QUEUE (durable := true)
  NuropbRMQ.basicPublish c 1 "hello-nuropb-rmq".toUTF8 "" q
    { deliveryMode := some 2, contentType := some "text/plain" } (wantConfirm := true)
  IO.println "sent b'hello-nuropb-rmq'"
  NuropbRMQ.close c
