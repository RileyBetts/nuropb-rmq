/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope

open Std.Async
open NuropbRMQ
open NuropbRmq.Pattern.Envelope

/-- One session, eight in-flight stub RPCs on the Std.Async loop. -/
def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let q := "nr.bench.lean.overlap"
  let srvConn ← connect cfg
  let _ ← openChannel srvConn 1
  let _ ← queueDeclare srvConn 1 q (autoDelete := true)
  let _ ← basicConsume srvConn 1 q
  let srv : RpcServer := {
    conn := srvConn
    queue := q
    handler := fun _ _ => pure (.obj [("ok", .bool true)])
  }
  let sess ← liftM (mkSession cfg)
  Session.start sess
  let cli : RpcClient := { session := sess }
  let reqs := List.replicate 8 (q, "bench.echo", Json.obj [("b", .str "x")])
  background (prio := .dedicated) (RpcServer.serveAsync srv)
  sleep (Std.Time.Millisecond.Offset.ofNat 50)
  let rs ← RpcClient.requestAll cli reqs
  if rs.length != 8 then
    throw (IO.userError s!"expected 8 replies, got {rs.length}")
  liftM (IO.println "lean_rpc_overlap: ok")
  Session.close sess
  close srvConn
