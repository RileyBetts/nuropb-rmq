/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Errors
import NuropbRmq.Pattern.Envelope
import NuropbRMQ.Connection

namespace NuropbRMQ

open NuropbRmq.Pattern.Envelope
open NuropbRmq.Pattern.Errors

structure DlqTimeoutProcessor where
  conn : AmqpConnection
  dlqName : String
  channelId : Nat := 1
  unroutableReplies : IO.Ref Nat

def DlqTimeoutProcessor.start (cfg : ConnectionConfig) (dlqName : String) : IO DlqTimeoutProcessor := do
  let c ← connect cfg
  let _ ← openChannel c 1
  let _ ← queueDeclare c 1 dlqName (durable := true)
  let _ ← basicConsume c 1 dlqName
  return { conn := c, dlqName, unroutableReplies := ← IO.mkRef 0 }

def DlqTimeoutProcessor.close (p : DlqTimeoutProcessor) : IO Unit :=
  NuropbRMQ.close p.conn

def DlqTimeoutProcessor.step (p : DlqTimeoutProcessor) : IO Unit := do
  let msg ← receive p.conn 5000
  match msg.properties.replyTo, msg.properties.correlationId with
  | some rt, some corr =>
    if rt ≠ "" then
      let body := encodeError REQUEST_TIMEOUT "request timed out" (some corr) (.obj [
        ("code_name", .str "REQUEST_TIMEOUT"), ("retryable", .bool true),
        ("correlation_id", .str corr),
      ])
      try
        basicPublish p.conn p.channelId body "" rt
          { contentType := some "application/json", correlationId := some corr }
          (mandatory := true)
      catch _ =>
        p.unroutableReplies.modify (· + 1)
  | _, _ => pure ()
  basicAck p.conn p.channelId msg.deliveryTag

end NuropbRMQ
