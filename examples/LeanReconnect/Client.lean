/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope

open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def ping (sess : Session) : IO Json :=
  RpcClient.request { session := sess } "demo.ping" "demo.ping" (.obj []) none
    Examples.Common.MESH_EXCHANGE

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let park ← mkSession cfg { failOutstanding := false }
  Session.start park
  let _ ← ping park
  Session.reconnect park
  let _ ← ping park
  Session.close park
  let fail ← mkSession cfg { failOutstanding := true }
  Session.start fail
  let _ ← Session.register fail (some "fail-fast-01")
  unless (← fail.pending.get).contains "fail-fast-01" do
    throw (IO.userError "register did not record pending")
  Session.reconnect fail
  unless (← fail.pending.get).isEmpty do
    throw (IO.userError "fail-fast reconnect left pending")
  Session.close fail
  IO.println "reconnect: ok park then fail-fast"
