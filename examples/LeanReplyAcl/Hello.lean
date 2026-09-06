/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRmq.Protocol.Methods

/-!
Live reply-forge 403. Management-API users are created by the smoke script.
Expects `channel.close` 403 on a default-exchange publish to another `nr.reply.*`.
-/

open Std.Async
open NuropbRmq.Protocol
open NuropbRMQ

def envOr (key default : String) : IO String :=
  return (← IO.getEnv key).getD default

def expectForgeDenied (c : AmqpConnection) (victim : String) : Async Unit := do
  try
    basicPublish c 1 "forge".toUTF8 "" victim {} (mandatory := true)
    throw (IO.userError "expected channel.close 403, publish succeeded")
  catch e =>
    let msg := toString e
    if msg.contains "channel.close 403" then
      pure ()
    else
      throw e

def main : IO Unit := Examples.Common.runAsync do
  let base ← liftM Examples.Common.cfg
  let client ← liftM (envOr "NUROPB_RMQ_ACL_CLIENT" "")
  let svc ← liftM (envOr "NUROPB_RMQ_ACL_SVC" "")
  let pw ← liftM (envOr "NUROPB_RMQ_ACL_PASSWORD" "acl-test-secret")
  let victim ← liftM (envOr "NUROPB_RMQ_ACL_VICTIM" "")
  if client.isEmpty || svc.isEmpty || victim.isEmpty then
    throw (IO.userError "set NUROPB_RMQ_ACL_CLIENT, NUROPB_RMQ_ACL_SVC, NUROPB_RMQ_ACL_VICTIM")

  let admin ← connect base
  let _ ← openChannel admin 1
  let _ ← queueDeclare admin 1 victim (durable := false) (exclusive := false)
    (autoDelete := true)
  close admin

  let forge ← connect { base with username := client, password := pw }
  let _ ← openChannel forge 1
  expectForgeDenied forge victim
  try close forge catch _ => pure ()
  liftM (IO.println "reply-acl: forge denied 403")

  let service ← connect { base with username := svc, password := pw }
  let _ ← openChannel service 1
  basicPublish service 1 "ok".toUTF8 "" victim {}
    (mandatory := true) (wantConfirm := true)
  close service
  liftM (IO.println "reply-acl: service publish ok")
