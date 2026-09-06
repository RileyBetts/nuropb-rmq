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
  if method.endsWith ".ping" then return .obj [("pong", .bool true)]
  if method.endsWith ".echo" then return .obj [("echo", params)]
  return .obj [("ok", .bool true)]

partial def serveLoop (srv : RpcServer) (events : EventPublisher) : Async Unit := do
  try
    let msg ← receive srv.conn 60000
    RpcServer.serveOnce srv msg
    EventPublisher.publish events "" "interop.request_handled" (.obj [])
  catch e =>
    liftM (IO.eprintln s!"[service] {e}")
  serveLoop srv events

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let mesh ← liftM (mkMeshService cfg { service := Examples.Common.INTEROP_SERVICE } ["ping", "echo"])
  let q ← MeshService.start mesh
  let conn ← liftM (MeshService.connection mesh)
  let events ← EventPublisher.start cfg Examples.Common.INTEROP_EVENTS "fanout"
  let inst ← liftM Socket.hexId
  MeshRegistryPublisher.announce conn 1 {
    service := Examples.Common.INTEROP_SERVICE
    methods := ["ping", "echo"]
    instanceId := inst
    queue := q
    exchange := Examples.Common.MESH_EXCHANGE
    publishedAt := (← liftM IO.monoMsNow) / 1000
    ttlS := 30
  }
  let _ ← basicConsume conn 1 q
  liftM (IO.println "[service] listening identity='interop' methods=['ping', 'echo'] mesh='nr.mesh' (Ctrl-C to stop)")
  liftM ((← IO.getStdout).flush)
  serveLoop { conn, queue := q, handler := handle } events
