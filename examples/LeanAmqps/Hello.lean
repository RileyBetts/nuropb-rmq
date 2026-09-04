/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRMQTls

/-!
tls-verify-full smoke. Requires AMQPS env (NUROPB_RMQ_TLS=1, CA, hostname).
-/

open Std.Async
open NuropbRMQ

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  unless cfg.tls do
    throw (IO.userError "set NUROPB_RMQ_TLS=1 (and CA / hostname) for lean_amqps_hello")
  let c ← NuropbRMQTls.connectAsync cfg
  let _ ← openChannel c 1
  let q ← queueDeclare c 1 "nr.ex.amqps" (durable := true)
  basicPublish c 1 "hello-amqps".toUTF8 "" q
    { deliveryMode := some 2, contentType := some "text/plain" } (wantConfirm := true)
  let _ ← basicConsume c 1 q
  let msg ← receive c 10000
  basicAck c 1 msg.deliveryTag
  let text := (String.fromUTF8? msg.body).getD ""
  if text != "hello-amqps" then
    throw (IO.userError s!"unexpected body '{text}'")
  liftM (IO.println s!"amqps: ok received '{text}'")
  close c
