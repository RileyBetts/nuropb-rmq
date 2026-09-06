/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope

open Std.Async
open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def ping (sess : Session) : Async Json :=
  RpcClient.request { session := sess } "demo.ping" "demo.ping" (.obj []) none
    Examples.Common.MESH_EXCHANGE

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let park ← liftM (mkSession cfg { failOutstanding := false })
  Session.start park
  let _ ← ping park
  Session.reconnect park
  let _ ← ping park
  Session.close park
  let fail ← liftM (mkSession cfg { failOutstanding := true })
  Session.start fail
  let _ ← liftM (Session.register fail (some "fail-fast-01"))
  unless (← liftM (fail.pending.get : IO (List String))).contains "fail-fast-01" do
    throw (IO.userError "register did not record pending")
  Session.reconnect fail
  unless (← liftM (fail.pending.get : IO (List String))).isEmpty do
    throw (IO.userError "fail-fast reconnect left pending")
  Session.close fail
  liftM (IO.println "reconnect: ok park then fail-fast")
