/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Pattern mesh namespace model.

Mirrors SpeC++ `in_namespace` / `BindOutcome` and Python
`nuropb_rmq.patterns.mesh` client-side refuse-before-bind.
Broker ACL is an external axiom — not proved here.
-/

namespace NuropbRmq.Pattern.Mesh

abbrev ServiceName := String
abbrev RoutingKey := String

/-- SpeC++ `in_namespace`: exact service key or `service.` prefix. -/
def inNamespace (service : ServiceName) (rk : RoutingKey) : Bool :=
  (rk == service) || (service ++ ".").isPrefixOf rk

inductive BindOutcome where
  | bindOk
  | bindRefused
  deriving DecidableEq, Repr

/-- Client-side bind guard: namespaced → BindOk, else BindRefused. -/
def tryBind (service : ServiceName) (rk : RoutingKey) : BindOutcome :=
  if inNamespace service rk then .bindOk else .bindRefused

end NuropbRmq.Pattern.Mesh
