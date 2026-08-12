; Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
; Released under Apache 2.0 license as described in the file LICENSE.

; Negative Pattern checks: namespace violation or auth fail-closed break → UNSAT
(set-logic ALL)
(set-info :status unsat)

(declare-datatypes () ((AuthOutcome AuthOk AuthReject AuthPublicSkip)))
(declare-datatypes () ((BindOutcome BindOk BindRefused)))

(declare-const service_name String)
(declare-const routing_key String)
(declare-const method_name String)
(declare-const correlation_id String)
(declare-const jwt_jti String)
(declare-const jwt_method String)
(declare-const jwt_valid_sig Bool)
(declare-const jwt_expired Bool)
(declare-const claims_present Bool)
(declare-const method_is_public Bool)
(declare-const auth_outcome AuthOutcome)
(declare-const bind_outcome BindOutcome)

(define-fun in_namespace () Bool
  (or (= routing_key service_name)
      (str.prefixof (str.++ service_name ".") routing_key)))

(assert (= bind_outcome (ite in_namespace BindOk BindRefused)))

(assert (= auth_outcome
  (ite method_is_public AuthPublicSkip
  (ite (not claims_present) AuthReject
  (ite (not jwt_valid_sig) AuthReject
  (ite jwt_expired AuthReject
  (ite (not (= jwt_jti correlation_id)) AuthReject
  (ite (not (= jwt_method method_name)) AuthReject
       AuthOk))))))))

; Forced contradictions
(assert (= service_name "orders"))
(assert (= routing_key "payments.charge"))
(assert (= bind_outcome BindOk))

(assert (not method_is_public))
(assert (not claims_present))
(assert (= auth_outcome AuthOk))

(check-sat)
