/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Protocol.Methods

/-!
Live reply-forge 403. Management-API users are created by the smoke script.
Expects `channel.close` 403 on a default-exchange publish to another `nr.reply.*`.
-/

open NuropbRmq.Protocol

def envOr (key default : String) : IO String :=
  return (← IO.getEnv key).getD default

def expectForgeDenied (c : NuropbRMQ.AmqpConnection) (victim : String) : IO Unit := do
  try
    NuropbRMQ.basicPublish c 1 "forge".toUTF8 "" victim {} (mandatory := true)
    let _ ← NuropbRMQ.expectMethod c.st 1 CHANNEL CHANNEL_CLOSE
    throw (IO.userError "expected channel.close 403, publish succeeded")
  catch e =>
    let msg := toString e
    if msg.contains "channel.close 403" then
      pure ()
    else
      throw e

def main : IO Unit := do
  let base ← Examples.Common.cfg
  let client ← envOr "NUROPB_RMQ_ACL_CLIENT" ""
  let svc ← envOr "NUROPB_RMQ_ACL_SVC" ""
  let pw ← envOr "NUROPB_RMQ_ACL_PASSWORD" "acl-test-secret"
  let victim ← envOr "NUROPB_RMQ_ACL_VICTIM" ""
  if client.isEmpty || svc.isEmpty || victim.isEmpty then
    throw (IO.userError "set NUROPB_RMQ_ACL_CLIENT, NUROPB_RMQ_ACL_SVC, NUROPB_RMQ_ACL_VICTIM")

  let admin ← NuropbRMQ.connect base
  let _ ← NuropbRMQ.openChannel admin 1
  let _ ← NuropbRMQ.queueDeclare admin 1 victim (durable := false) (exclusive := false)
    (autoDelete := true)
  NuropbRMQ.close admin

  let forge ← NuropbRMQ.connect { base with username := client, password := pw }
  let _ ← NuropbRMQ.openChannel forge 1
  expectForgeDenied forge victim
  try NuropbRMQ.close forge catch _ => pure ()
  IO.println "reply-acl: forge denied 403"

  let service ← NuropbRMQ.connect { base with username := svc, password := pw }
  let _ ← NuropbRMQ.openChannel service 1
  NuropbRMQ.basicPublish service 1 "ok".toUTF8 "" victim {}
    (mandatory := true) (wantConfirm := true)
  NuropbRMQ.close service
  IO.println "reply-acl: service publish ok"
