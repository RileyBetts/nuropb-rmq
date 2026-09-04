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

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let sub ← EventSubscriber.start cfg Examples.Common.INTEROP_EVENTS "fanout"
  let sess ← liftM (mkSession cfg)
  Session.start sess
  let cli : RpcClient := { session := sess }
  let ping ← RpcClient.request cli "interop.ping" "interop.ping" (.obj []) none Examples.Common.MESH_EXCHANGE
  liftM (IO.println s!"[client] RPC interop.ping -> {encodeJson ping}")
  let echo ← RpcClient.request cli "interop.echo" "interop.echo" (.obj [("hello", .str "world")]) none Examples.Common.MESH_EXCHANGE
  liftM (IO.println s!"[client] RPC interop.echo -> {encodeJson echo}")
  try
    let (meth, _) ← EventSubscriber.receive sub 5000
    liftM (IO.println s!"[client] event {meth}")
  catch _ =>
    liftM (IO.println "[client] timed out waiting for events")
  liftM (IO.println "[client] done")
  Session.close sess
  EventSubscriber.close sub
