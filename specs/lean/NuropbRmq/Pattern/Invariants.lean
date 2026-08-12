/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Mesh
import NuropbRmq.Pattern.Claims

/-!
Pattern invariants: namespace bind refuse-before-send and fail-closed claims.
-/

namespace NuropbRmq.Pattern

open Mesh Claims

/-! ### Mesh namespace bind -/

theorem tryBind_ok_of_inNamespace (service : ServiceName) (rk : RoutingKey)
    (h : inNamespace service rk = true) :
    tryBind service rk = .bindOk := by
  simp [tryBind, h]

theorem tryBind_refused_of_not_inNamespace (service : ServiceName) (rk : RoutingKey)
    (h : inNamespace service rk = false) :
    tryBind service rk = .bindRefused := by
  simp [tryBind, h]

theorem tryBind_exact_service (service : ServiceName) :
    tryBind service service = .bindOk := by
  simp [tryBind, inNamespace]

/-- Concrete SpeC++ positive: `orders` / `orders.ping`. -/
theorem tryBind_orders_ping :
    tryBind "orders" "orders.ping" = .bindOk := by
  native_decide

/-- Concrete SpeC++ negative: foreign prefix refused. -/
theorem tryBind_foreign_refused :
    tryBind "orders" "payments.charge" = .bindRefused := by
  native_decide

/-! ### Claims public skip -/

theorem tryAuth_public_skip (i : AuthInput) (h : i.methodIsPublic = true) :
    tryAuth i = .authPublicSkip := by
  simp [tryAuth, h]

/-! ### Claims fail-closed -/

theorem tryAuth_reject_missing (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hmiss : i.claimsPresent = false) :
    tryAuth i = .authReject := by
  simp [tryAuth, hpub, hmiss]

theorem tryAuth_reject_bad_sig (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hpres : i.claimsPresent = true)
    (hbad : i.validSig = false) :
    tryAuth i = .authReject := by
  simp [tryAuth, hpub, hpres, hbad]

theorem tryAuth_reject_expired (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hpres : i.claimsPresent = true)
    (hsig : i.validSig = true) (hexp : i.expired = true) :
    tryAuth i = .authReject := by
  simp [tryAuth, hpub, hpres, hsig, hexp]

theorem tryAuth_reject_jti_mismatch (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hpres : i.claimsPresent = true)
    (hsig : i.validSig = true) (hexp : i.expired = false)
    (hjti : (i.jti == i.correlationId) = false) :
    tryAuth i = .authReject := by
  simp [tryAuth, hpub, hpres, hsig, hexp, hjti]

theorem tryAuth_reject_method_mismatch (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hpres : i.claimsPresent = true)
    (hsig : i.validSig = true) (hexp : i.expired = false)
    (hjti : (i.jti == i.correlationId) = true)
    (hmeth : (i.jwtMethod == i.rpcMethod) = false) :
    tryAuth i = .authReject := by
  simp [tryAuth, hpub, hpres, hsig, hexp, hjti, hmeth]

/-! ### Claims AuthOk -/

theorem tryAuth_ok (i : AuthInput)
    (hpub : i.methodIsPublic = false) (hpres : i.claimsPresent = true)
    (hsig : i.validSig = true) (hexp : i.expired = false)
    (hjti : (i.jti == i.correlationId) = true)
    (hmeth : (i.jwtMethod == i.rpcMethod) = true) :
    tryAuth i = .authOk := by
  simp [tryAuth, hpub, hpres, hsig, hexp, hjti, hmeth]

theorem authRequired_iff_not_public (i : AuthInput) :
    authRequired i = !i.methodIsPublic := rfl

/-- Concrete SpeC++ positive auth world. -/
theorem tryAuth_orders_ping_ok :
    tryAuth
      { methodIsPublic := false
        claimsPresent := true
        validSig := true
        expired := false
        jti := "abc"
        correlationId := "abc"
        jwtMethod := "orders.ping"
        rpcMethod := "orders.ping" } = .authOk := by
  native_decide

/-- Concrete SpeC++ fail-closed: missing claims. -/
theorem tryAuth_missing_reject :
    tryAuth
      { methodIsPublic := false
        claimsPresent := false
        validSig := true
        expired := false
        jti := "abc"
        correlationId := "abc"
        jwtMethod := "orders.ping"
        rpcMethod := "orders.ping" } = .authReject := by
  native_decide

end NuropbRmq.Pattern
