/-!
Pattern claims / auth-required model.

Mirrors SpeC++ `AuthOutcome` decision tree and Python
`nuropb_rmq.patterns.context.AuthConfig.verify_request`.

JWT cryptography is opaque: `validSig` / `expired` are Bool inputs,
not HS256 proofs.
-/

namespace NuropbRmq.Pattern.Claims

abbrev ClaimId := String
abbrev MethodName := String

structure AuthInput where
  methodIsPublic : Bool
  claimsPresent : Bool
  validSig : Bool
  expired : Bool
  jti : ClaimId
  correlationId : ClaimId
  jwtMethod : MethodName
  rpcMethod : MethodName
  deriving Repr

inductive AuthOutcome where
  | authOk
  | authReject
  | authPublicSkip
  deriving DecidableEq, Repr

/-- Fail-closed auth decision tree (SpeC++ `auth_outcome`). -/
def tryAuth (i : AuthInput) : AuthOutcome :=
  if i.methodIsPublic then .authPublicSkip
  else if !i.claimsPresent then .authReject
  else if !i.validSig then .authReject
  else if i.expired then .authReject
  else if !(i.jti == i.correlationId) then .authReject
  else if !(i.jwtMethod == i.rpcMethod) then .authReject
  else .authOk

/-- Auth is required when the method is not public. -/
def authRequired (i : AuthInput) : Bool :=
  !i.methodIsPublic

end NuropbRmq.Pattern.Claims
