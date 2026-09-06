/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import NuropbRmq.Pattern.Envelope
import NuropbRMQ.Connection

namespace NuropbRMQ

open Std.Async
open NuropbRmq.Pattern.Envelope
open NuropbRmq.Protocol

structure EventPublisher where
  conn : AmqpConnection
  exchange : String
  exchangeType : String := "topic"
  channelId : Nat := 1
  wantConfirm : Bool := false
  mandatory : Bool := false

def EventPublisher.start (cfg : ConnectionConfig) (exchange : String)
    (exchangeType : String := "topic")
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial)
    (durableExchange : Bool := false)
    (wantConfirm : Bool := false)
    (mandatory : Bool := false) : Async EventPublisher := do
  let c ← dial cfg
  let _ ← openChannel c 1
  exchangeDeclare c 1 exchange exchangeType
    (durable := durableExchange) (autoDelete := !durableExchange)
  if wantConfirm then
    confirmSelectAsync c 1
  return { conn := c, exchange, exchangeType, wantConfirm, mandatory }

def EventPublisher.close (p : EventPublisher) : Async Unit :=
  NuropbRMQ.close p.conn

def EventPublisher.publish (p : EventPublisher) (routingKey method : String) (params : Json) :
    Async Unit := do
  let key := if p.exchangeType == "fanout" then "" else routingKey
  let body := encodeNotification method (some params)
  let props : BasicProperties := {
    contentType := some "application/json"
    deliveryMode := if p.wantConfirm then some 2 else none
  }
  basicPublishAsync p.conn p.channelId body p.exchange key props
    (mandatory := p.mandatory) (wantConfirm := p.wantConfirm)

structure EventSubscriber where
  conn : AmqpConnection
  exchange : String
  channelId : Nat := 1

def EventSubscriber.start (cfg : ConnectionConfig) (exchange : String)
    (exchangeType : String := "topic") (bindingKey : String := "#")
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial)
    (queue : String := "")
    (exclusive : Bool := true)
    (autoDelete : Bool := true)
    (durable : Bool := false)
    (durableExchange : Bool := false) : Async EventSubscriber := do
  if durable && queue == "" then
    throw (IO.userError "durable EventSubscriber requires a named queue")
  let exclusive := if durable then false else exclusive
  let autoDelete := if durable then false else autoDelete
  let c ← dial cfg
  let _ ← openChannel c 1
  exchangeDeclare c 1 exchange exchangeType
    (durable := durableExchange) (autoDelete := !durableExchange)
  let q ← queueDeclare c 1 queue (durable := durable) (exclusive := exclusive)
    (autoDelete := autoDelete)
  let bindKey := if exchangeType == "fanout" then "" else bindingKey
  queueBind c 1 q exchange bindKey
  let _ ← basicConsume c 1 q
  return { conn := c, exchange }

def EventSubscriber.close (s : EventSubscriber) : Async Unit :=
  NuropbRMQ.close s.conn

/-- Ack after a successful decode. Invalid envelopes are not acked. -/
def EventSubscriber.receive (s : EventSubscriber) (timeoutMs : Nat := 5000) :
    Async (String × Json) := do
  let msg ← receiveAsync s.conn timeoutMs
  match decodeNotification msg.body with
  | .ok pair =>
    basicAckAsync s.conn s.channelId msg.deliveryTag
    return pair
  | .error _ =>
    throw (IO.userError "INVALID_ENVELOPE")

end NuropbRMQ
