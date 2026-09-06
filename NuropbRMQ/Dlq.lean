/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import NuropbRmq.Pattern.Errors
import NuropbRmq.Pattern.Envelope
import NuropbRMQ.Connection

namespace NuropbRMQ

open Std.Async
open NuropbRmq.Pattern.Envelope
open NuropbRmq.Pattern.Errors

structure DlqTimeoutProcessor where
  conn : AmqpConnection
  dlqName : String
  channelId : Nat := 1
  unroutableReplies : IO.Ref Nat

def DlqTimeoutProcessor.start (cfg : ConnectionConfig) (dlqName : String)
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async DlqTimeoutProcessor := do
  let c ← dial cfg
  let _ ← openChannel c 1
  let _ ← queueDeclare c 1 dlqName (durable := true)
  let _ ← basicConsume c 1 dlqName
  return { conn := c, dlqName, unroutableReplies := ← ioRun (IO.mkRef 0) }

def DlqTimeoutProcessor.close (p : DlqTimeoutProcessor) : Async Unit :=
  NuropbRMQ.close p.conn

def DlqTimeoutProcessor.step (p : DlqTimeoutProcessor) : Async Unit := do
  let msg ← receiveAsync p.conn 5000
  match msg.properties.replyTo, msg.properties.correlationId with
  | some rt, some corr =>
    if rt ≠ "" then
      let body := encodeError REQUEST_TIMEOUT "request timed out" (some corr) (.obj [
        ("code_name", .str "REQUEST_TIMEOUT"), ("retryable", .bool true),
        ("correlation_id", .str corr),
      ])
      try
        basicPublishAsync p.conn p.channelId body "" rt
          { contentType := some "application/json", correlationId := some corr }
          (mandatory := true)
      catch _ =>
        ioRun (p.unroutableReplies.modify (· + 1))
  | _, _ => pure ()
  basicAckAsync p.conn p.channelId msg.deliveryTag

end NuropbRMQ
