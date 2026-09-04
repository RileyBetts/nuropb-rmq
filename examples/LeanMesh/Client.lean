/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope

open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let sess ← mkSession cfg
  Session.start sess
  let cli : RpcClient := { session := sess }
  let ping ← RpcClient.request cli "demo.ping" "demo.ping" (.obj []) none Examples.Common.MESH_EXCHANGE
  IO.println s!"[client] RPC demo.ping -> {encodeJson ping}"
  let echo ← RpcClient.request cli "demo.echo" "demo.echo" (.obj [("hello", .str "world")]) none Examples.Common.MESH_EXCHANGE
  IO.println s!"[client] RPC demo.echo -> {encodeJson echo}"
  IO.println "[client] done"
  Session.close sess
