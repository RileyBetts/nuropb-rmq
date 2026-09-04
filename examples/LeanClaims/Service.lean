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

def handle (method : String) (_params : Json) : IO Json := do
  if method.endsWith ".ping" || method == "ping" then
    return .obj [("pong", .bool true)]
  return .obj [("ok", .bool true)]

/-- Deny when params contain `"deny": true` (Lean `authorize_func` smoke). -/
def authorize (_claims method : String) (params : Json) : IO Bool := do
  let _ := method
  match params with
  | .obj kvs =>
    match kvs.find? (fun p => p.1 == "deny") with
    | some (_, .bool true) => return false
    | _ => return true
  | _ => return true

partial def serveLoop (srv : RpcServer) : Async Unit := do
  try
    let msg ← receive srv.conn 60000
    RpcServer.serveOnce srv msg
  catch e =>
    liftM (IO.eprintln s!"[claims-service] {e}")
  serveLoop srv

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let mesh ← liftM (mkMeshService cfg { service := "orders" } ["ping"])
  let q ← MeshService.start mesh
  let conn ← liftM (MeshService.connection mesh)
  let _ ← basicConsume conn 1 q
  liftM (IO.println "[claims-service] listening identity='orders' auth=HS256 (Ctrl-C to stop)")
  liftM ((← IO.getStdout).flush)
  serveLoop {
    conn, queue := q, handler := handle
    auth := some { jwtSecret := "test-secret", authorize := some authorize }
  }
