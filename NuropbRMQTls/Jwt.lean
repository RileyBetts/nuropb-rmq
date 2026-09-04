/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Crypto.Base64Url
import NuropbRmq.Pattern.Jwt
import NuropbRmq.Pattern.Claims

/-!
RS256 / ES256 compact verify via OpenSSL FFI. Not linked by default `lake build`.
HMAC hardness is out of scope. Audience / issuer are not checked (same as Lean HS256).
-/

namespace NuropbRMQ.Tls

open NuropbRmq.Crypto
open NuropbRmq.Pattern.Jwt
open NuropbRmq.Pattern.Claims

@[extern "nuropb_jwt_verify_asymmetric"]
opaque verifyAsymmetricSig (alg pemPub signing : @& String) (sig : @& ByteArray) : IO Bool

def verifyAsymmetric
    (wantAlg pemPub token : String)
    (now : Nat)
    (correlationId rpcMethod : String)
    (methodIsPublic : Bool) : IO AuthOutcome := do
  if methodIsPublic then return .authPublicSkip
  if pemPub.isEmpty then return .authReject
  match splitCompact token with
  | none => return .authReject
  | some (h64, p64, s64) =>
    match decodeJsonPart h64, decodeJsonPart p64, decodeBase64Url s64 with
    | some header, some payload, some sig =>
      if findStringField header "alg" != some wantAlg then return .authReject
      let signing := h64 ++ "." ++ p64
      let ok ←
        try verifyAsymmetricSig wantAlg pemPub signing sig
        catch _ => pure false
      if !ok then return .authReject
      match findNatField payload "exp",
            findStringField payload "jti",
            findStringField payload "method" with
      | some exp, some jti, some meth =>
        let expired := decide (exp ≤ now)
        return tryAuth {
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
      | _, _, _ => return .authReject
    | _, _, _ => return .authReject

def verifyRs256 (pemPub token : String) (now : Nat)
    (correlationId rpcMethod : String) (methodIsPublic : Bool := false) : IO AuthOutcome :=
  verifyAsymmetric "RS256" pemPub token now correlationId rpcMethod methodIsPublic

def verifyEs256 (pemPub token : String) (now : Nat)
    (correlationId rpcMethod : String) (methodIsPublic : Bool := false) : IO AuthOutcome :=
  verifyAsymmetric "ES256" pemPub token now correlationId rpcMethod methodIsPublic

/-- PyJWT RS256 golden (exp 2000000000, jti corr-id-01, method orders.ping). -/
def goldenRs256Pub : String :=
  "-----BEGIN PUBLIC KEY-----\n" ++
  "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAv5vGGwRn1wcRwSjqzxVJ\n" ++
  "mvfRRGOMioxCfqxSng8sXvM+lgSJDwQ8nF1xTTBP48Af/00QwxGmG1486QY4Q/9c\n" ++
  "NAvVuB/07pwKI+fD4OvZRCoUuwkFiYs6t6bO7osge3Jzzl5I1y08sVlpJ8/HnKpD\n" ++
  "TpCPeKcWoxFy5mwDraJuP4si9BvDOviMSJMOh8j+i5SUoN/lBmPJUj9kplDxemDk\n" ++
  "Cw9u/jOTBaiIwPQI6GbEiekjVGp5VAGQMit46NSQUbI2nX+HLMbQtsrcGTl/HxcY\n" ++
  "K7VO2ZpiPhSkH3n+0ZUHivpsdRMGyI1DyqKCgcqrlRcWCBjFfb9j9jFBw6793H80\n" ++
  "AwIDAQAB\n" ++
  "-----END PUBLIC KEY-----\n"

def goldenRs256Token : String :=
  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9." ++
  "eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9." ++
  "hYQWLaIhO22oQY1jQuURKYxO5z_s87ofbFfvPZpDLF36JBSYVIhPOwHDDLHeTrPU5BOo96s930AhHrHpZYJu-VrHdFprRBH9mOloP-aNjhvkiGWQkpiUuFyR2k2TRLqerIgqhGILzAry_wj90XEDXSPAVa4XzUMM6uJDVoDHHiyV9wNxGRXZilIg2XePakKuh68Yti4JHyCj_Du-7byXy60FCaIl8sQL_h1seuHfUuYqRQN2Rp-bNdreORpy1GcxSpy6Mj5dEccxsnYxD6vyswX6tBD26sBMSev2e3II6iJZQ6h2NaCrkj7xnpEGuf6B80R5eAtXwgOqHJbYn66R4w"

/-- PyJWT ES256 golden (P-256). -/
def goldenEs256Pub : String :=
  "-----BEGIN PUBLIC KEY-----\n" ++
  "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEVE13xqh7qyP+5c5ta3rGYEPxaF20\n" ++
  "CvTALOGUFo+cYCOphrZkAN3RO5G84E55sKUsPArqBELP6iNgZACMuCmfcg==\n" ++
  "-----END PUBLIC KEY-----\n"

def goldenEs256Token : String :=
  "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9." ++
  "eyJleHAiOjIwMDAwMDAwMDAsImp0aSI6ImNvcnItaWQtMDEiLCJtZXRob2QiOiJvcmRlcnMucGluZyJ9." ++
  "UIpa9vBktltZeATYBjoblQFZ4S7QYRVBdnPCsws1uJpAziRId2KveWVkKhUFzC1XPbzkRkF6_uKki-IU6tb48Q"

end NuropbRMQ.Tls
