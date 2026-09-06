/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ
import NuropbRmq.Pattern.Envelope
import NuropbRmq.Pattern.Jwt

open Std.Async
open NuropbRmq.Pattern.Envelope
open NuropbRMQ

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let sess ← liftM (mkSession cfg)
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
    sleep (Std.Time.Millisecond.Offset.ofNat 400)
  unless denied do
    throw (IO.userError s!"expected UNAUTHORIZED without claims, last={last}")
  let ping ← RpcClient.request cli "orders.ping" "orders.ping" (.obj [])
    (some "corr-id-01") Examples.Common.MESH_EXCHANGE (some NuropbRmq.Pattern.Jwt.goldenToken)
  let mut authDenied := false
  let mut authLast := ""
  try
    let _ ← RpcClient.request cli "orders.ping" "orders.ping"
      (.obj [("deny", .bool true)]) (some "corr-id-01")
      Examples.Common.MESH_EXCHANGE (some NuropbRmq.Pattern.Jwt.goldenToken)
    authLast := "authorize hook allowed deny=true"
  catch e =>
    authLast := toString e
    authDenied := authLast.contains "UNAUTHORIZED" || authLast.contains "-33100"
      || authLast.contains "unauthorized"
  unless authDenied do
    throw (IO.userError s!"expected UNAUTHORIZED from authorize hook, last={authLast}")
  liftM (IO.println s!"claims: ok unauthorized then {encodeJson ping} then authorize-deny")
  Session.close sess
