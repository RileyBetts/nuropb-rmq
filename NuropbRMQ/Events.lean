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

structure EventPublisher where
  conn : AmqpConnection
  exchange : String
  exchangeType : String := "topic"
  channelId : Nat := 1

def EventPublisher.start (cfg : ConnectionConfig) (exchange : String)
    (exchangeType : String := "topic")
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async EventPublisher := do
  let c ← dial cfg
  let _ ← openChannel c 1
  exchangeDeclare c 1 exchange exchangeType (autoDelete := true)
  return { conn := c, exchange, exchangeType }

def EventPublisher.close (p : EventPublisher) : Async Unit :=
  NuropbRMQ.close p.conn

def EventPublisher.publish (p : EventPublisher) (routingKey method : String) (params : Json) :
    Async Unit := do
  let key := if p.exchangeType == "fanout" then "" else routingKey
  let body := encodeNotification method (some params)
  basicPublishAsync p.conn p.channelId body p.exchange key { contentType := some "application/json" }

structure EventSubscriber where
  conn : AmqpConnection
  exchange : String
  channelId : Nat := 1

def EventSubscriber.start (cfg : ConnectionConfig) (exchange : String)
    (exchangeType : String := "topic") (bindingKey : String := "#")
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async EventSubscriber := do
  let c ← dial cfg
  let _ ← openChannel c 1
  exchangeDeclare c 1 exchange exchangeType (autoDelete := true)
  let q ← queueDeclare c 1 "" (exclusive := true) (autoDelete := true)
  queueBind c 1 q exchange bindingKey
  let _ ← basicConsume c 1 q
  return { conn := c, exchange }

def EventSubscriber.close (s : EventSubscriber) : Async Unit :=
  NuropbRMQ.close s.conn

def EventSubscriber.receive (s : EventSubscriber) (timeoutMs : Nat := 5000) :
    Async (String × Json) := do
  let msg ← receiveAsync s.conn timeoutMs
  basicAckAsync s.conn s.channelId msg.deliveryTag
  match decodeNotification msg.body with
  | .ok pair => return pair
  | .error _ => throw (IO.userError "INVALID_ENVELOPE")

end NuropbRMQ
