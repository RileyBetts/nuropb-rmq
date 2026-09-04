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

def handle (method : String) (params : Json) : IO Json := do
  if method.endsWith ".ping" || method == "ping" then
    return .obj [("pong", .bool true)]
  if method.endsWith ".echo" || method == "echo" then
    return .obj [("echo", params)]
  return .obj [("ok", .bool true)]

partial def serveLoop (srv : RpcServer) (events : EventPublisher) : Async Unit := do
  try
    let msg ← receive srv.conn 60000
    RpcServer.serveOnce srv msg
    EventPublisher.publish events "" "demo.request_handled" (.obj [])
  catch e =>
    liftM (IO.eprintln s!"[service] {e}")
  serveLoop srv events

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let mesh ← liftM (mkMeshService cfg { service := "demo" } ["ping", "echo"])
  let q ← MeshService.start mesh
  let conn ← liftM (MeshService.connection mesh)
  let events ← EventPublisher.start cfg "nr.demo.events" "fanout"
  let _ ← basicConsume conn 1 q
  liftM (IO.println "[service] listening identity='demo' methods=['ping', 'echo'] mesh='nr.mesh' (Ctrl-C to stop)")
  liftM ((← IO.getStdout).flush)
  serveLoop { conn, queue := q, handler := handle } events
