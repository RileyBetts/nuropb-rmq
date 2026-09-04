/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope
import NuropbRmq.Pattern.Errors

open NuropbRmq.Pattern.Envelope
open NuropbRmq.Pattern.Errors
open NuropbRMQ

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let id ← Socket.hexId
  let work := s!"nr.ex.lean.ttl.{id}"
  let dlq := s!"nr.ex.lean.dlq.{id}"
  let dlx := s!"nr.ex.lean.dlx.{id}"
  let c ← connect cfg
  let _ ← openChannel c 1
  let _ ← queueDeclareProfile c 1 work (durable := true) (ttlMs := some 400)
    (dlx := some dlx) (dlrk := some "timeout")
  let _ ← queueDeclare c 1 dlq (durable := true)
  queueBind c 1 dlq dlx "timeout"
  let reply ← queueDeclare c 1 "" (exclusive := true) (autoDelete := true)
  let _ ← basicConsume c 1 reply
  basicPublish c 1 "dlq-probe".toUTF8 "" work
    { deliveryMode := some 2, replyTo := some reply, correlationId := some "dlq-1" }
    (wantConfirm := true)
  IO.sleep 800
  let proc ← DlqTimeoutProcessor.start cfg dlq
  DlqTimeoutProcessor.step proc
  let msg ← receive c 8000
  basicAck c 1 msg.deliveryTag
  match decodeResponse msg.body with
  | .ok (.err code _ _) =>
    if code != REQUEST_TIMEOUT then
      throw (IO.userError s!"expected REQUEST_TIMEOUT, got {code}")
  | _ => throw (IO.userError "expected JSON-RPC timeout error")
  IO.println "dlq: ok REQUEST_TIMEOUT"
  DlqTimeoutProcessor.close proc
  NuropbRMQ.close c
