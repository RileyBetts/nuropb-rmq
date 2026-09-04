/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope
import NuropbRmq.Pattern.Jwt

open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let sess ← mkSession cfg
  Session.start sess
  let cli : RpcClient := { session := sess }
  let mut denied := false
  let mut last := ""
  for _ in [0:8] do
    try
      let _ ← RpcClient.request cli "orders.ping" "orders.ping" (.obj []) none
        Examples.Common.MESH_EXCHANGE
      last := "request succeeded without claims"
    catch e =>
      last := toString e
      denied := last.contains "UNAUTHORIZED" || last.contains "-33100"
        || last.contains "unauthorized"
    if denied then break
    IO.sleep 400
  unless denied do
    throw (IO.userError s!"expected UNAUTHORIZED without claims, last={last}")
  let ping ← RpcClient.request cli "orders.ping" "orders.ping" (.obj [])
    (some "corr-id-01") Examples.Common.MESH_EXCHANGE (some NuropbRmq.Pattern.Jwt.goldenToken)
  IO.println s!"claims: ok unauthorized then {encodeJson ping}"
  Session.close sess
