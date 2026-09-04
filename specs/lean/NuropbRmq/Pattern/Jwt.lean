/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Crypto.Hmac
import NuropbRmq.Crypto.Base64Url
import NuropbRmq.Pattern.Claims

/-!
Executable HS256 JWT compact verify (correspondence with PyJWT + AuthConfig).
RS256/ES256 and HMAC hardness are out of scope.
-/

namespace NuropbRmq.Pattern.Jwt

open NuropbRmq.Crypto
open NuropbRmq.Pattern.Claims

def splitCompact (token : String) : Option (String × String × String) :=
  match token.splitOn "." with
  | [h, p, s] => some (h, p, s)
  | _ => none

def afterNeedle (json needle : String) : Option String :=
  match json.splitOn needle with
  | [_, rest] => some rest
  | _ :: rest :: _ => some rest
  | _ => none

/-- Extract `"key":"..."` from a JSON object (JWT payload/header subset). -/
def findStringField (json key : String) : Option String :=
  match afterNeedle json ("\"" ++ key ++ "\":\"") with
  | none => none
  | some rest =>
      match rest.splitOn "\"" with
      | val :: _ => some val
      | [] => none

/-- Extract `"key":<nat>` (no quotes). -/
def findNatField (json key : String) : Option Nat :=
  match afterNeedle json ("\"" ++ key ++ "\":") with
  | none => none
  | some rest =>
      let digits := rest.takeWhile (fun c => c.isDigit)
      if digits.isEmpty then none else digits.toNat?

def decodeJsonPart (b64 : String) : Option String :=
  match decodeBase64Url b64 with
  | none => none
  | some bytes => String.fromUTF8? bytes

/-- Decoded JWT payload JSON (for the IO `authorize` hook). -/
def payloadJson (token : String) : Option String :=
  match splitCompact token with
  | none => none
  | some (_, p64, _) => decodeJsonPart p64

def byteEq (a b : ByteArray) : Bool :=
  a.size == b.size &&
    Id.run do
      let mut ok := true
      for i in [0:a.size] do
        if a.get! i != b.get! i then ok := false
      pure ok

/-- HS256 verify + claim binding. `now` is unix seconds (discrete). -/
def verifyHs256
    (secret token : String)
    (now : Nat)
    (correlationId rpcMethod : String)
    (methodIsPublic : Bool) : AuthOutcome :=
  if methodIsPublic then .authPublicSkip
  else
    match splitCompact token with
    | none => .authReject
    | some (h64, p64, s64) =>
        match decodeJsonPart h64, decodeJsonPart p64, decodeBase64Url s64 with
        | some header, some payload, some sig =>
            let alg := findStringField header "alg"
            if alg != some "HS256" then .authReject
            else
              let signing := (h64 ++ "." ++ p64).toUTF8
              let mac := hmacSha256 secret.toUTF8 signing
              if !byteEq mac sig then .authReject
              else
                match findNatField payload "exp",
                      findStringField payload "jti",
                      findStringField payload "method" with
                | some exp, some jti, some meth =>
                    let expired := decide (exp ≤ now)
                    tryAuth {
                      methodIsPublic := false
                      claimsPresent := true
                      validSig := true
                      expired := expired
                      jti := jti
                      correlationId := correlationId
                      jwtMethod := meth
                      rpcMethod := rpcMethod
                      authorizeOk := true
                    }
                | _, _, _ => .authReject
        | _, _, _ => .authReject

/-- PyJWT HS256 golden (secret `test-secret`, exp 2000000000, jti corr-id-01). -/
def goldenToken : String :=
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9.2rsdzXvOcSa21j8nUHDxV0B4v_163qqxsITHhpuozeg"

theorem golden_hs256_authOk :
    verifyHs256 "test-secret" goldenToken 1700000000 "corr-id-01" "orders.ping" false =
      AuthOutcome.authOk := by
  native_decide

theorem golden_hs256_expired :
    verifyHs256 "test-secret" goldenToken 2000000001 "corr-id-01" "orders.ping" false =
      AuthOutcome.authReject := by
  native_decide

theorem golden_hs256_unbound_jti :
    verifyHs256 "test-secret" goldenToken 1700000000 "other-id" "orders.ping" false =
      AuthOutcome.authReject := by
  native_decide

theorem golden_hs256_bad_secret :
    verifyHs256 "wrong-secret" goldenToken 1700000000 "corr-id-01" "orders.ping" false =
      AuthOutcome.authReject := by
  native_decide

theorem golden_hs256_public_skip :
    verifyHs256 "test-secret" goldenToken 1700000000 "corr-id-01" "orders.ping" true =
      AuthOutcome.authPublicSkip := by
  native_decide

end NuropbRmq.Pattern.Jwt
