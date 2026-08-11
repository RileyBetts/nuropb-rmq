; SpeC++ Pattern: mesh namespace bind + auth-required claims (Phase step 6).
; CheckSat must return sat.
(set-logic ALL)
(set-info :status sat)

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
(declare-const auth_required Bool)
(declare-const auth_outcome AuthOutcome)
(declare-const bind_outcome BindOutcome)

(define-fun in_namespace () Bool
  (or (= routing_key service_name)
      (str.prefixof (str.++ service_name ".") routing_key)))

(assert (= bind_outcome (ite in_namespace BindOk BindRefused)))

(assert (= auth_required (not method_is_public)))

(assert (= auth_outcome
  (ite method_is_public AuthPublicSkip
  (ite (not claims_present) AuthReject
  (ite (not jwt_valid_sig) AuthReject
  (ite jwt_expired AuthReject
  (ite (not (= jwt_jti correlation_id)) AuthReject
  (ite (not (= jwt_method method_name)) AuthReject
       AuthOk))))))))

; Positive world: namespaced bind + verified claims on auth-required method
(assert (= service_name "orders"))
(assert (= routing_key "orders.ping"))
(assert (= method_name "orders.ping"))
(assert (= correlation_id "abc"))
(assert (= jwt_jti "abc"))
(assert (= jwt_method "orders.ping"))
(assert jwt_valid_sig)
(assert (not jwt_expired))
(assert claims_present)
(assert (not method_is_public))
(assert (= bind_outcome BindOk))
(assert (= auth_outcome AuthOk))

(check-sat)
(get-model)
