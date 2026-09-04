/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQTls
import NuropbRmq.Pattern.Claims
import NuropbRmq.Pattern.Jwt

/-!
IO smoke: OpenSSL RS256 / ES256 verify against PyJWT goldens.
No broker. Build: `lake build lean_jwt_asymmetric` (links libssl).
-/

open NuropbRMQ.Tls
open NuropbRmq.Pattern.Claims

def expect (label : String) (got want : AuthOutcome) : IO Unit := do
  unless got == want do
    throw (IO.userError s!"{label}: got {repr got} want {repr want}")

def main : IO Unit := do
  let now := 1700000000
  expect "RS256" (← verifyRs256 goldenRs256Pub goldenRs256Token now "corr-id-01" "orders.ping")
    .authOk
  expect "ES256" (← verifyEs256 goldenEs256Pub goldenEs256Token now "corr-id-01" "orders.ping")
    .authOk
  expect "RS256 bad key" (← verifyRs256 goldenEs256Pub goldenRs256Token now "corr-id-01" "orders.ping")
    .authReject
  expect "ES256 missing key" (← verifyEs256 "" goldenEs256Token now "corr-id-01" "orders.ping")
    .authReject
  expect "alg mismatch" (← verifyRs256 goldenRs256Pub goldenEs256Token now "corr-id-01" "orders.ping")
    .authReject
  expect "unknown alg via HS256 path"
    (NuropbRmq.Pattern.Jwt.verifyHs256 "test-secret" goldenRs256Token now "corr-id-01" "orders.ping" false)
    .authReject
  expect "RS256 expired" (← verifyRs256 goldenRs256Pub goldenRs256Token 2000000001 "corr-id-01" "orders.ping")
    .authReject
  expect "RS256 unbound jti" (← verifyRs256 goldenRs256Pub goldenRs256Token now "other-id" "orders.ping")
    .authReject
  IO.println "jwt-asym: ok"
