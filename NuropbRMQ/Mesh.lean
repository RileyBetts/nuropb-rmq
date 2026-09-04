/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Mesh
import NuropbRmq.Pattern.Errors
import NuropbRMQ.Connection
import NuropbRMQ.Socket

namespace NuropbRMQ

open NuropbRmq.Pattern.Mesh
open NuropbRmq.Pattern.Errors

def DEFAULT_MESH_EXCHANGE : String := "nr.mesh"

structure ServiceIdentity where
  service : String
  deriving Repr

def ServiceIdentity.namespacePrefix (id : ServiceIdentity) : String :=
  id.service ++ "."

def ServiceIdentity.routingKey (id : ServiceIdentity) (method : String) : String :=
  id.service ++ "." ++ method

def ServiceIdentity.inNamespace (id : ServiceIdentity) (rk : String) : Bool :=
  NuropbRmq.Pattern.Mesh.inNamespace id.service rk && (rk.splitOn ".." |>.length) ≤ 1

structure MeshService where
  config : ConnectionConfig
  identity : ServiceIdentity
  methods : List String
  exchange : String := DEFAULT_MESH_EXCHANGE
  queueName : String
  channelId : Nat := 1
  announce : Bool := false
  conn : IO.Ref (Option AmqpConnection)
  queue : IO.Ref (Option String)

def mkMeshService (cfg : ConnectionConfig) (identity : ServiceIdentity) (methods : List String)
    (exchange : String := DEFAULT_MESH_EXCHANGE) (announce : Bool := false) : IO MeshService := do
  if methods.isEmpty then throw (IO.userError "methods must be non-empty")
  return {
    config := cfg, identity, methods, exchange, announce
    queueName := s!"nr.svc.{identity.service}"
    conn := ← IO.mkRef none
    queue := ← IO.mkRef none
  }

def MeshService.assertBindAllowed (m : MeshService) (rk : String) : IO String := do
  match tryBind m.identity.service rk with
  | .bindOk =>
    if (rk.splitOn ".." |>.length) > 1 then throw (IO.userError "BIND_REFUSED")
    return rk
  | .bindRefused => throw (IO.userError "BIND_REFUSED")

def MeshService.start (m : MeshService) : IO String := do
  let c ← connect m.config
  let _ ← openChannel c m.channelId
  exchangeDeclare c m.channelId m.exchange "direct" (durable := true)
  let q ← queueDeclareProfile c m.channelId m.queueName (durable := true)
    (dlx := some s!"nr.dlx.{m.identity.service}") (ttlMs := some 60000)
    (queueType := "quorum") (dlrk := some "timeout") (deliveryLimit := some 10)
  for meth in m.methods do
    let key := m.identity.routingKey meth
    let _ ← MeshService.assertBindAllowed m key
    queueBind c m.channelId q m.exchange key
  m.conn.set (some c)
  m.queue.set (some q)
  return q

def MeshService.close (m : MeshService) : IO Unit := do
  if let some c := (← m.conn.get) then
    try NuropbRMQ.close c catch _ => pure ()
  m.conn.set none
  m.queue.set none

def MeshService.rebind (m : MeshService) : IO String := do
  try MeshService.close m catch _ => pure ()
  MeshService.start m

def MeshService.connection (m : MeshService) : IO AmqpConnection := do
  match ← m.conn.get with
  | some c => return c
  | none => throw (IO.userError "mesh service not started")

end NuropbRMQ
