/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/
/-
Lean vs Python IO remasure (PLAIN firehose or AMQPS serial). Not a product target.
-/
import Std.Async
import NuropbRMQ
import NuropbRMQTls
import NuropbRmq.Pattern.Envelope

open Std.Async
open NuropbRMQ
open NuropbRmq.Pattern.Envelope

def envNat (key : String) (fallback : Nat) : IO Nat := do
  match (← IO.getEnv key) with
  | none => return fallback
  | some s => return s.toNat?.getD fallback

def fill (n : Nat) (b : UInt8) : ByteArray :=
  ByteArray.mk (Array.replicate n b)

def padStr (n : Nat) : String :=
  String.ofList (List.replicate n 'y')

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

def runRawFirehose (count size : Nat) (queue : String) : Async Unit := do
  let cfg ← ioRun envConfig
  let c ← dial cfg
  let _ ← openChannel c 1
  let q ← queueDeclare c 1 queue (exclusive := true) (autoDelete := true)
  let _ ← basicConsume c 1 q
  let body := fill size 0x78
  let done ← IO.Promise.new
  background do
    for _ in [0:count] do
      let msg ← receive c 120000
      basicAck c 1 msg.deliveryTag
    ioRun (done.resolve ())
  sleep (Std.Time.Millisecond.Offset.ofNat 20)
  let t0 ← ioRun IO.monoNanosNow
  for _ in [0:count] do
    basicPublish c 1 body "" q { contentType := some "application/octet-stream" }
      (wantConfirm := false)
  match ← Async.ofTask done.result? with
  | some _ => pure ()
  | none => throw (IO.userError "firehose consume dropped")
  let t1 ← ioRun IO.monoNanosNow
  let wall := (t1 - t0).toFloat / 1e9
  let rate := if wall > 0 then count.toFloat / wall else 0
  ioRun (IO.println s!"lean raw_firehose size={size} count={count} msgs_per_sec={rate} wall={wall}")
  close c

partial def requestWindows (cli : RpcClient) (q : String) (params : Json) (left : Nat) : Async Unit := do
  if left == 0 then return
  let n := min 32 left
  let reqs := List.replicate n (q, "bench.echo", params)
  let _ ← RpcClient.requestAll cli reqs
  requestWindows cli q params (left - n)

def runRpc (count size : Nat) (queue : String) (overlap : Bool) : Async Unit := do
  let cfg ← ioRun envConfig
  let srvConn ← dial cfg
  let _ ← openChannel srvConn 1
  let q ← queueDeclare srvConn 1 queue (exclusive := true) (autoDelete := true)
  let _ ← basicConsume srvConn 1 q
  let srv : RpcServer := {
    conn := srvConn
    queue := q
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
    requestWindows cli q params count
  else
    for _ in [0:count] do
      let _ ← RpcClient.request cli q "bench.echo" params
  let t1 ← ioRun IO.monoNanosNow
  let wall := (t1 - t0).toFloat / 1e9
  let rate := if wall > 0 then count.toFloat / wall else 0
  let scen := if overlap then "rpc_overlap" else "rpc_serial"
  ioRun (IO.println s!"lean {scen} size={size} count={count} msgs_per_sec={rate} wall={wall}")
  Session.close sess
  close srvConn

def main : IO Unit := (do
  let mode := (← ioRun (IO.getEnv "NUROPB_BENCH_MODE")).getD "raw"
  let count ← ioRun (envNat "NUROPB_BENCH_COUNT" 200)
  let size ← ioRun (envNat "NUROPB_BENCH_SIZE" 64)
  let queue := (← ioRun (IO.getEnv "NUROPB_BENCH_QUEUE")).getD "nr.bench.lean"
  if mode == "rpc" then
    runRpc count size queue false
  else if mode == "rpc_overlap" then
    runRpc count size queue true
  else if mode == "raw_serial" then
    runRawSerial count size queue
  else
    runRawFirehose count size queue
  : Async Unit).block
