/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRMQTls

/-!
mTLS + SASL EXTERNAL smoke. Requires AMQPS env plus client PEM
(`NUROPB_RMQ_CERT_FILE`, `NUROPB_RMQ_KEY_FILE`). Not a default lake target.
-/

open Std.Async
open NuropbRMQ

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  unless cfg.tls do
    throw (IO.userError "set NUROPB_RMQ_TLS=1 (and CA / hostname) for lean_amqps_mtls")
  unless cfg.hasClientCert do
    throw (IO.userError "set client PEM (CERT_FILE+KEY_FILE) or NUROPB_RMQ_PKCS12_FILE for mTLS")
  let c ← NuropbRMQTls.connectAsync cfg
  let _ ← openChannel c 1
  let q ← queueDeclare c 1 "nr.ex.amqps.mtls" (durable := true)
  basicPublish c 1 "hello-mtls".toUTF8 "" q
    { deliveryMode := some 2, contentType := some "text/plain" } (wantConfirm := true)
  let _ ← basicConsume c 1 q
  let msg ← receive c 10000
  basicAck c 1 msg.deliveryTag
  let text := (String.fromUTF8? msg.body).getD ""
  if text != "hello-mtls" then
    throw (IO.userError s!"unexpected body '{text}'")
  liftM (IO.println s!"amqps-mtls: ok received '{text}'")
  close c
