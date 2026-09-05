/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/
/-
Lean vs Python IO remasure. Not a product target.
Raw firehose uses two connections (pub ∥ consume), matching Python.
RPC topologies: exclusive classic, nr.mesh + classic durable, nr.mesh + quorum.
-/
import Std.Async
import NuropbRMQ
import NuropbRMQTls
import NuropbRmq.Pattern.Envelope

open Std.Async
open NuropbRMQ
open NuropbRmq.Pattern.Envelope

def MESH_EXCHANGE : String := "nr.mesh"

def envNat (key : String) (fallback : Nat) : IO Nat := do
  match (← IO.getEnv key) with
  | none => return fallback
  | some s => return s.toNat?.getD fallback

def fill (n : Nat) (b : UInt8) : ByteArray :=
  ByteArray.mk (Array.replicate n b)

def padStr (n : Nat) : String :=
  String.ofList (List.replicate n 'y')

def benchId : IO String :=
  NuropbRMQ.Socket.hexId

def dial (cfg : ConnectionConfig) : Async AmqpConnection :=
  if cfg.tls then NuropbRMQTls.connectAsync cfg else connectAsync cfg

partial def serveN (srv : RpcServer) (n : Nat) : Async Unit := do
  if n == 0 then return
  let msg ← receive srv.conn 120000
  RpcServer.serveOnce srv msg
  serveN srv (n - 1)

def runRawSerial (count size : Nat) (queue : String) : Async Unit := do
  let cfg ← ioRun envConfig
  let c ← dial cfg
  let _ ← openChannel c 1
  let q ← queueDeclare c 1 queue (exclusive := true) (autoDelete := true)
  let _ ← basicConsume c 1 q
  let body := fill size 0x78
  let t0 ← ioRun IO.monoNanosNow
  for _ in [0:count] do
    basicPublish c 1 body "" q { contentType := some "application/octet-stream" }
      (wantConfirm := true)
    let msg ← receive c 120000
    basicAck c 1 msg.deliveryTag
  let t1 ← ioRun IO.monoNanosNow
  let wall := (t1 - t0).toFloat / 1e9
  let rate := if wall > 0 then count.toFloat / wall else 0
  ioRun (IO.println s!"lean raw_serial size={size} count={count} msgs_per_sec={rate} wall={wall}")
  close c

/-- Dual-connection firehose: consume+ack on `cons`, publish on `pub`. -/
def runRawFirehose (count size : Nat) (queue : String) : Async Unit := do
  let cfg ← ioRun envConfig
  let cons ← dial cfg
  let pub ← dial cfg
  let _ ← openChannel cons 1
  let _ ← openChannel pub 1
  let q ← queueDeclare cons 1 queue (exclusive := true) (autoDelete := true)
  let _ ← basicConsume cons 1 q
  let body := fill size 0x78
  let done ← IO.Promise.new
  background do
    for _ in [0:count] do
      let msg ← receive cons 120000
      basicAck cons 1 msg.deliveryTag
    ioRun (done.resolve ())
  sleep (Std.Time.Millisecond.Offset.ofNat 20)
  let t0 ← ioRun IO.monoNanosNow
  for _ in [0:count] do
    basicPublish pub 1 body "" q { contentType := some "application/octet-stream" }
      (wantConfirm := false)
  match ← Async.ofTask done.result? with
  | some _ => pure ()
  | none => throw (IO.userError "firehose consume dropped")
  let t1 ← ioRun IO.monoNanosNow
  let wall := (t1 - t0).toFloat / 1e9
  let rate := if wall > 0 then count.toFloat / wall else 0
  ioRun (IO.println s!"lean raw_firehose size={size} count={count} msgs_per_sec={rate} wall={wall}")
  close pub
  close cons

partial def requestWindows (cli : RpcClient) (target method : String) (params : Json)
    (exchange : String) (left : Nat) : Async Unit := do
  if left == 0 then return
  let n := min 32 left
  let reqs := List.replicate n (target, method, params)
  let _ ← RpcClient.requestAll cli reqs (exchange := exchange)
  requestWindows cli target method params exchange (left - n)

inductive RpcTopo where
  | classic
  | meshClassic
  | meshQuorum

def RpcTopo.tag : RpcTopo → String
  | .classic => "rpc_classic"
  | .meshClassic => "rpc_mesh_classic"
  | .meshQuorum => "rpc_mesh_quorum"

structure RpcSetup where
  srvConn : AmqpConnection
  queue : String
  target : String
  method : String
  exchange : String
  closeSrv : Async Unit

def setupClassic (cfg : ConnectionConfig) (queue : String) : Async RpcSetup := do
  let srvConn ← dial cfg
  let _ ← openChannel srvConn 1
  let q ← queueDeclare srvConn 1 queue (exclusive := true) (autoDelete := true)
  let _ ← basicConsume srvConn 1 q
  return {
    srvConn, queue := q, target := q, method := "echo", exchange := ""
    closeSrv := close srvConn
  }

def setupMeshClassic (cfg : ConnectionConfig) : Async RpcSetup := do
  let id ← ioRun benchId
  let svc := s!"b{id}"
  let srvConn ← dial cfg
  let _ ← openChannel srvConn 1
  exchangeDeclare srvConn 1 MESH_EXCHANGE "direct" (durable := true)
  let qName := s!"nr.svc.{svc}"
  let q ← queueDeclareProfile srvConn 1 qName (durable := true)
    (dlx := some s!"nr.dlx.{svc}") (ttlMs := some 60000)
    (queueType := "classic") (dlrk := some "timeout")
  let key := s!"{svc}.echo"
  queueBind srvConn 1 q MESH_EXCHANGE key
  let _ ← basicConsume srvConn 1 q
  return {
    srvConn, queue := q, target := key, method := "echo", exchange := MESH_EXCHANGE
    closeSrv := close srvConn
  }

def setupMeshQuorum (cfg : ConnectionConfig) : Async RpcSetup := do
  let id ← ioRun benchId
  let svc := s!"b{id}"
  let mesh ← ioRun (mkMeshService cfg { service := svc } ["echo"])
  let q ← MeshService.start mesh dial
  let srvConn ← ioRun (MeshService.connection mesh)
  let _ ← basicConsume srvConn 1 q
  return {
    srvConn, queue := q, target := s!"{svc}.echo", method := "echo", exchange := MESH_EXCHANGE
    closeSrv := MeshService.close mesh
  }

def runRpc (count size : Nat) (queue : String) (overlap : Bool) (topo : RpcTopo) : Async Unit := do
  let cfg ← ioRun envConfig
  let setup ←
    match topo with
    | .classic => setupClassic cfg queue
    | .meshClassic => setupMeshClassic cfg
    | .meshQuorum => setupMeshQuorum cfg
  let srv : RpcServer := {
    conn := setup.srvConn
    queue := setup.queue
    handler := fun _ _ => pure (.obj [("ok", .bool true)])
  }
  background (serveN srv count)
  sleep (Std.Time.Millisecond.Offset.ofNat 50)
  let sess ← ioRun (mkSession cfg)
  Session.startAsync sess dial
  let cli : RpcClient := { session := sess }
  let params := Json.obj [("b", .str (padStr size))]
  let t0 ← ioRun IO.monoNanosNow
  if overlap then
    requestWindows cli setup.target setup.method params setup.exchange count
  else
    for _ in [0:count] do
      let _ ← RpcClient.request cli setup.target setup.method params none setup.exchange
  let t1 ← ioRun IO.monoNanosNow
  let wall := (t1 - t0).toFloat / 1e9
  let rate := if wall > 0 then count.toFloat / wall else 0
  let scen := if overlap then s!"{topo.tag}_overlap" else topo.tag
  ioRun (IO.println s!"lean {scen} size={size} count={count} msgs_per_sec={rate} wall={wall}")
  Session.close sess
  setup.closeSrv

def parseTopo (mode : String) : Option (RpcTopo × Bool) :=
  if mode == "rpc" || mode == "rpc_classic" then some (.classic, false)
  else if mode == "rpc_overlap" || mode == "rpc_classic_overlap" then some (.classic, true)
  else if mode == "rpc_mesh_classic" then some (.meshClassic, false)
  else if mode == "rpc_mesh_classic_overlap" then some (.meshClassic, true)
  else if mode == "rpc_mesh_quorum" then some (.meshQuorum, false)
  else if mode == "rpc_mesh_quorum_overlap" then some (.meshQuorum, true)
  else none

def main : IO Unit := (do
  let mode := (← ioRun (IO.getEnv "NUROPB_BENCH_MODE")).getD "raw"
  let count ← ioRun (envNat "NUROPB_BENCH_COUNT" 200)
  let size ← ioRun (envNat "NUROPB_BENCH_SIZE" 64)
  let queue := (← ioRun (IO.getEnv "NUROPB_BENCH_QUEUE")).getD "nr.bench.lean"
  match parseTopo mode with
  | some (topo, overlap) => runRpc count size queue overlap topo
  | none =>
    if mode == "raw_serial" then
      runRawSerial count size queue
    else
      runRawFirehose count size queue
  : Async Unit).block
