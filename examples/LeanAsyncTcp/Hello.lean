/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Std.Async.TCP
import NuropbRMQ.AsyncTransport
import NuropbRMQ.Connection

open Std.Async
open Std.Net

/-- Loopback send/recv with native `Async` (zero `.block` on this path). -/
def echoAsync (port : UInt16) : Async Unit := do
  let srv ← TCP.Socket.Server.mk
  liftM (srv.bind (.v4 { addr := IPv4Addr.ofParts 127 0 0 1, port }))
  liftM (srv.listen 8)
  background (prio := .dedicated) do
    let peer ← srv.accept
    let t := NuropbRMQ.tcpTransportAsync peer
    match ← t.recv? 16 with
    | some b => t.send b
    | none => throw (IO.userError "server eof")
  sleep (Std.Time.Millisecond.Offset.ofNat 80)
  let cli ← NuropbRMQ.connectTcpAsync "127.0.0.1" port
  let clientT := NuropbRMQ.tcpTransportAsync cli
  clientT.send "ping".toUTF8
  match ← clientT.recv? 16 with
  | some b =>
    if (String.fromUTF8? b).getD "" != "ping" then
      throw (IO.userError "async echo mismatch")
  | none => throw (IO.userError "client eof")
  let io := NuropbRMQ.Transport.ofAsync clientT
  liftM (io.send "pong".toUTF8)

/-- Register a reply waiter, deliver, await — no broker. -/
def waiterAsync : Async Unit := do
  let st ← liftM (IO.mkRef { (default : NuropbRMQ.ConnState) with closed := false })
  let want : NuropbRMQ.IncomingMessage := {
    deliveryTag := 1
    exchange := ""
    routingKey := "reply"
    body := "ok".toUTF8
    properties := { correlationId := some "rid-1" }
    redelivered := false
    consumerTag := "ctag"
  }
  background (prio := .dedicated) do
    sleep (Std.Time.Millisecond.Offset.ofNat 20)
    NuropbRMQ.ioRun (NuropbRMQ.offerDeliver st want)
  let got ← NuropbRMQ.waitReplyWaiterAsync st "rid-1" 1000
  if got.properties.correlationId != some "rid-1" then
    throw (IO.userError "waiter correlation mismatch")

/-- No-broker Std.Async.TCP smoke: refused dial, loopback send/recv (no `.block`
    on the Async path), then the same ops through `Transport.ofAsync`. -/
def main : IO Unit := do
  let port : UInt16 := 18765
  try
    let _ ← NuropbRMQ.connectTcpAsync "127.0.0.1" 1 |>.block
    IO.println "FAIL: expected refused connect"
    return
  catch _ =>
    pure ()
  echoAsync port |>.block
  waiterAsync |>.block
  IO.println "lean_async_tcp: ok"
