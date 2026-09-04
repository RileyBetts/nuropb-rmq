/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRMQTls

/-!
tls-verify-full smoke. Requires AMQPS env (NUROPB_RMQ_TLS=1, CA, hostname).
-/

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  unless cfg.tls do
    throw (IO.userError "set NUROPB_RMQ_TLS=1 (and CA / hostname) for lean_amqps_hello")
  let c ← NuropbRMQTls.connect cfg
  let _ ← NuropbRMQ.openChannel c 1
  let q ← NuropbRMQ.queueDeclare c 1 "nr.ex.amqps" (durable := true)
  NuropbRMQ.basicPublish c 1 "hello-amqps".toUTF8 "" q
    { deliveryMode := some 2, contentType := some "text/plain" } (wantConfirm := true)
  let _ ← NuropbRMQ.basicConsume c 1 q
  let msg ← NuropbRMQ.receive c 10000
  NuropbRMQ.basicAck c 1 msg.deliveryTag
  let text := (String.fromUTF8? msg.body).getD ""
  if text != "hello-amqps" then
    throw (IO.userError s!"unexpected body '{text}'")
  IO.println s!"amqps: ok received '{text}'"
  NuropbRMQ.close c
