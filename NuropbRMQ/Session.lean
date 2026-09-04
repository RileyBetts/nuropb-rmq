/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Session.Correlation
import NuropbRmq.Session.Reconnect
import NuropbRmq.Session.Ids
import NuropbRmq.Pattern.Errors
import NuropbRMQ.Connection
import NuropbRMQ.Socket

namespace NuropbRMQ

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
    pending := ← IO.mkRef []
    parked := ← IO.mkRef []
    replies := ← IO.mkRef []
    epoch := ← IO.mkRef 0
    policy
    started := ← IO.mkRef false
  }

def Session.start (s : Session) : IO Unit := do
  let c ← connect s.config
  let _ ← openChannel c s.channelId
  let id ← Socket.hexId
  let q ← queueDeclare c s.channelId s!"nr.reply.{id}" (exclusive := true) (autoDelete := true)
  let _ ← basicConsume c s.channelId q
  s.conn.set c
  s.replyQueue.set (some q)
  s.started.set true

def Session.close (s : Session) : IO Unit := do
  s.started.set false
  s.pending.set []
  s.parked.set []
  s.replyQueue.set none
  try NuropbRMQ.close (← s.conn.get) catch _ => pure ()

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

partial def Session.drainReplies (s : Session) : IO Unit := do
  let c ← s.conn.get
  try
    let msg ← receive c 50
    s.replies.modify (msg :: ·)
    Session.drainReplies s
  catch _ => pure ()

partial def Session.waitReplyUntil (s : Session) (rid : String) (deadline : Nat) : IO IncomingMessage := do
  Session.drainReplies s
  let found := (← s.replies.get).find? (fun m => m.properties.correlationId == some rid)
  match found with
  | some msg =>
    s.replies.modify fun xs => xs.filter (fun m => m.properties.correlationId != some rid)
    let c ← s.conn.get
    basicAck c s.channelId msg.deliveryTag
    Session.forget s rid
    return msg
  | none =>
    if (← IO.monoMsNow) ≥ deadline then
      throw (IO.userError "REQUEST_TIMEOUT")
    IO.sleep 20
    Session.waitReplyUntil s rid deadline

def Session.waitReply (s : Session) (rid : String) (timeoutMs : Nat := 60000) : IO IncomingMessage := do
  Session.waitReplyUntil s rid ((← IO.monoMsNow) + timeoutMs)

def Session.reconnect (s : Session) : IO Unit := do
  let fail := s.policy.failOutstanding
  s.started.set false
  if fail then
    s.pending.set []
    s.parked.set []
  try NuropbRMQ.close (← s.conn.get) catch _ => pure ()
  s.replyQueue.set none
  s.epoch.modify (· + 1)
  Session.start s
  unless fail do
    let parked ← s.parked.get
    let c ← s.conn.get
    let q := (← s.replyQueue.get).getD ""
    for (rid, env) in parked do
      let props := { env.properties with replyTo := some q, correlationId := some rid }
      try
        basicPublish c s.channelId env.body env.exchange env.routingKey props env.mandatory true
      catch e =>
        Session.forget s rid
        throw e

end NuropbRMQ
