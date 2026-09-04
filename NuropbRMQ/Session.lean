/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import NuropbRmq.Session.Correlation
import NuropbRmq.Session.Reconnect
import NuropbRmq.Session.Ids
import NuropbRmq.Pattern.Errors
import NuropbRMQ.Connection
import NuropbRMQ.Socket

namespace NuropbRMQ

open Std.Async
open NuropbRmq.Session
open NuropbRmq.Session.Ids
open NuropbRmq.Pattern.Errors
open NuropbRmq.Protocol

structure ParkedPublish where
  exchange : String
  routingKey : String
  body : ByteArray
  properties : BasicProperties
  mandatory : Bool := true

structure ReconnectPolicy where
  maxAttempts : Nat := 5
  initialBackoffMs : Nat := 50
  maxBackoffMs : Nat := 2000
  failOutstanding : Bool := false
  deriving Repr

structure Session where
  config : ConnectionConfig
  conn : IO.Ref AmqpConnection
  channelId : Nat := 1
  replyQueue : IO.Ref (Option String)
  /-- Cached after `start` so RPC does not `ioRun` both refs every call. -/
  rpcCache : IO.Ref (Option (AmqpConnection × String))
  pending : IO.Ref (List String)
  parked : IO.Ref (List (String × ParkedPublish))
  replies : IO.Ref (List IncomingMessage)
  epoch : IO.Ref Nat
  policy : ReconnectPolicy
  started : IO.Ref Bool

def Session.replyQueueOpen (s : Session) : IO Bool := do
  return (← s.replyQueue.get).isSome && (← s.started.get)

def mkSession (cfg : ConnectionConfig := {}) (policy : ReconnectPolicy := {}) : IO Session := do
  let dummy ← IO.mkRef {
    config := cfg
    st := ← IO.mkRef (default : ConnState)
  }
  -- overwritten in start
  return {
    config := cfg
    conn := dummy
    replyQueue := ← IO.mkRef none
    rpcCache := ← IO.mkRef none
    pending := ← IO.mkRef []
    parked := ← IO.mkRef []
    replies := ← IO.mkRef []
    epoch := ← IO.mkRef 0
    policy
    started := ← IO.mkRef false
  }

/-- `dial` defaults to PLAIN `connectAsync`. AMQPS passes `NuropbRMQTls.connectAsync`
    so `NuropbRMQ` does not import OpenSSL. -/
def Session.startAsync (s : Session)
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async Unit := do
  let c ← dial s.config
  let _ ← openChannel c s.channelId
  confirmSelectAsync c s.channelId
  let id ← ioRun Socket.hexId
  let q ← queueDeclare c s.channelId s!"nr.reply.{id}" (exclusive := true) (autoDelete := true)
  let _ ← basicConsume c s.channelId q
  ioRun (s.conn.set c)
  ioRun (s.replyQueue.set (some q))
  ioRun (s.rpcCache.set (some (c, q)))
  ioRun (s.started.set true)

def Session.start (s : Session)
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async Unit :=
  Session.startAsync s dial

def Session.rpcHandles (s : Session) : IO (AmqpConnection × String) := do
  match ← s.rpcCache.get with
  | some h => return h
  | none =>
    let c ← s.conn.get
    let q := (← s.replyQueue.get).getD ""
    s.rpcCache.set (some (c, q))
    return (c, q)

def Session.close (s : Session) : Async Unit := do
  ioRun (s.started.set false)
  ioRun (s.pending.set [])
  ioRun (s.parked.set [])
  ioRun (s.replyQueue.set none)
  ioRun (s.rpcCache.set none)
  try NuropbRMQ.close (← ioRun (s.conn.get : IO AmqpConnection)) catch _ => pure ()

def Session.register (s : Session) (requestId : Option String) : IO String := do
  unless (← s.replyQueueOpen) do throw (IO.userError "session not started")
  let rid ← match requestId with
    | some id =>
      if !validId id then throw (IO.userError "INVALID_ID")
      if (← s.pending.get).contains id then throw (IO.userError "ID_COLLISION")
      pure id
    | none => Socket.hexId
  s.pending.modify (rid :: ·)
  return rid

def Session.remember (s : Session) (rid : String) (p : ParkedPublish) : IO Unit :=
  s.parked.modify fun xs => (rid, p) :: xs

def Session.forget (s : Session) (rid : String) : IO Unit := do
  s.parked.modify fun xs => xs.filter (fun p => p.1 != rid)
  s.pending.modify fun xs => xs.filter (· != rid)

def Session.waitReplyAsync (s : Session) (rid : String) (timeoutMs : Nat := 60000) :
    Async IncomingMessage := do
  try
    let c ← ioRun (s.conn.get : IO AmqpConnection)
    let msg ← waitReplyWaiterAsync c.st rid timeoutMs
    basicAckAsync c s.channelId msg.deliveryTag
    ioRun (Session.forget s rid : IO Unit)
    return msg
  catch e =>
    ioRun (Session.forget s rid : IO Unit)
    throw e

def Session.waitReply (s : Session) (rid : String) (timeoutMs : Nat := 60000) :
    Async IncomingMessage :=
  Session.waitReplyAsync s rid timeoutMs

def Session.reconnect (s : Session)
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async Unit := do
  let fail := s.policy.failOutstanding
  ioRun (s.started.set false)
  if fail then
    ioRun (s.pending.set [])
    ioRun (s.parked.set [])
  try NuropbRMQ.close (← ioRun (s.conn.get : IO AmqpConnection)) catch _ => pure ()
  ioRun (s.replyQueue.set none)
  ioRun (s.rpcCache.set none)
  ioRun (s.epoch.modify (· + 1))
  Session.startAsync s dial
  unless fail do
    let parked ← ioRun (s.parked.get : IO (List (String × ParkedPublish)))
    let c ← ioRun (s.conn.get : IO AmqpConnection)
    let q := (← ioRun (s.replyQueue.get : IO (Option String))).getD ""
    for (rid, env) in parked do
      let props := { env.properties with replyTo := some q, correlationId := some rid }
      try
        basicPublishAsync c s.channelId env.body env.exchange env.routingKey props env.mandatory true
      catch e =>
        ioRun (Session.forget s rid : IO Unit)
        throw e

end NuropbRMQ
