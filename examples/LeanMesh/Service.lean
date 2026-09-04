/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope

open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def handle (method : String) (params : Json) : IO Json := do
  if method.endsWith ".ping" || method == "ping" then
    return .obj [("pong", .bool true)]
  if method.endsWith ".echo" || method == "echo" then
    return .obj [("echo", params)]
  return .obj [("ok", .bool true)]

partial def serveLoop (srv : RpcServer) (events : EventPublisher) : IO Unit := do
  let msg ← receive srv.conn 60000
  RpcServer.serveOnce srv msg
  EventPublisher.publish events "" "demo.request_handled" (.obj [])
  serveLoop srv events

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let mesh ← mkMeshService cfg { service := "demo" } ["ping", "echo"]
  let q ← MeshService.start mesh
  let conn ← MeshService.connection mesh
  let _ ← basicConsume conn 1 q
  IO.println "[service] listening identity='demo' methods=['ping', 'echo'] mesh='nr.mesh' (Ctrl-C to stop)"
  let events ← EventPublisher.start cfg "nr.demo.events" "fanout"
  serveLoop { conn, queue := q, handler := handle } events
