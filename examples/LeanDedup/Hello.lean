/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQ
import NuropbRmq.Pattern.Envelope

/-!
Process-local request-id dedup smoke. No broker: `handleRpc` twice with the
same id; handler runs once and both replies match.
-/

open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def main : IO Unit := do
  let calls ← IO.mkRef (0 : Nat)
  let handler (method : String) (_params : Json) : IO Json := do
    calls.modify (· + 1)
    return .obj [("method", .str method), ("n", .num (Int.ofNat (← calls.get)))]
  let ref ← IO.mkRef ({ cap := 8 } : DedupState)
  let msg : IncomingMessage := {
    deliveryTag := 1
    exchange := ""
    routingKey := "q"
    body := encodeRequest "echo.dedup" (.obj []) "rid-1"
    properties := { correlationId := some "rid-1", replyTo := some "nr.reply.x" }
    redelivered := false
    consumerTag := "c"
  }
  let a ← handleRpc handler none (some ref) msg
  let b ← handleRpc handler none (some ref) msg
  unless a == b do
    throw (IO.userError "dedup: reply bytes diverged")
  let n ← calls.get
  unless n == 1 do
    throw (IO.userError s!"dedup: expected 1 handler call, got {n}")
  IO.println "dedup: ok handler-once"

