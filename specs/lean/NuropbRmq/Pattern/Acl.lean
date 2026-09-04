/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Mesh

/-!
Executable nuropb ACL profiles (not RabbitMQ's full regex engine / HA).

`reply-publish-restricted`: services may write `nr.reply.*`; clients must not
(forge denied). `mesh-bind-namespaced`: configure only under the service prefix;
`tryBind` is the client-side subset of that gate.

`matchesRegex` is a scoped matcher (`^`, `$`, `\\.`, `.`, `*`/`+`/`{n}`,
`[0-9a-f]`, `|`) used for documented profiles rewritten as regex and one
narrower live 403. It is not PCRE / RabbitMQ's engine.
-/

namespace NuropbRmq.Pattern.Acl

open NuropbRmq.Pattern.Mesh

def matchesPrefix (pattern name : String) : Bool :=
  name == pattern || pattern.isPrefixOf name

def allowed (patterns : List String) (name : String) : Bool :=
  patterns.any (fun p => matchesPrefix p name)

structure Perms where
  configure : List String := []
  write : List String := []
  read : List String := []
  deriving Repr

def canConfigure (p : Perms) (name : String) : Bool := allowed p.configure name
def canPublish (p : Perms) (name : String) : Bool := allowed p.write name
def canRead (p : Perms) (name : String) : Bool := allowed p.read name

/-- Client: exclusive reply queue configure/read; mesh write only. -/
def replyPublishRestrictedClient : Perms :=
  { configure := ["nr.reply."]
    write := ["nr.mesh"]
    read := ["nr.reply."] }

/-- Service: may publish RPC replies and mesh traffic. -/
def replyPublishRestrictedService : Perms :=
  { configure := ["nr.svc.", "nr.reply."]
    write := ["nr.mesh", "nr.reply.", "nr.dlx."]
    read := ["nr.svc.", "nr.mesh", "nr.dlx."] }

def meshBindNamespaced (service : ServiceName) : Perms :=
  { configure := [service]
    write := [service, "nr.mesh"]
    read := [service, "nr.mesh"] }

/-! ### Scoped regex (documented profiles + narrower live ACL) -/

inductive Atom where
  | lit (c : Char)
  | any
  | cls (spec : String)
  deriving Repr, DecidableEq

inductive Quant where
  | one
  | star
  | plus
  | exactly (n : Nat)
  deriving Repr, DecidableEq

structure Piece where
  atom : Atom
  quant : Quant := .one
  deriving Repr

structure Alt where
  pieces : List Piece
  endAnchor : Bool := false
  deriving Repr

def charInClass (spec : String) (c : Char) : Bool :=
  let rec go : List Char → Bool
    | [] => false
    | a :: '-' :: b :: rest => (a ≤ c && c ≤ b) || go rest
    | a :: rest => a == c || go rest
  go spec.toList

def matchAtom (a : Atom) (c : Char) : Bool :=
  match a with
  | .lit x => x == c
  | .any => true
  | .cls spec => charInClass spec c

partial def parseAtom (cs : List Char) : Option (Atom × List Char) :=
  match cs with
  | [] => none
  | '\\' :: c :: rest => some (.lit c, rest)
  | '.' :: rest => some (.any, rest)
  | '[' :: rest =>
    let rec take (acc : String) : List Char → Option (String × List Char)
      | [] => none
      | ']' :: r => some (acc, r)
      | c :: r => take (acc.push c) r
    match take "" rest with
    | some (spec, r) => some (.cls spec, r)
    | none => none
  | c :: rest =>
    if c == '^' || c == '$' || c == '|' || c == '*' || c == '+' || c == '{' then none
    else some (.lit c, rest)

def parseNat (cs : List Char) : Option (Nat × List Char) :=
  let digits := cs.takeWhile Char.isDigit
  if digits.isEmpty then none
  else some ((String.ofList digits).toNat!, cs.drop digits.length)

def parseQuant (cs : List Char) : Option (Quant × List Char) :=
  match cs with
  | '*' :: r => some (.star, r)
  | '+' :: r => some (.plus, r)
  | '{' :: r =>
    match parseNat r with
    | some (n, '}' :: r') => some (.exactly n, r')
    | _ => none
  | _ => some (.one, cs)

partial def parsePieces (cs : List Char) : Option (List Piece × List Char) :=
  match cs with
  | [] => some ([], [])
  | '$' :: _ => some ([], cs)
  | '|' :: _ => some ([], cs)
  | _ =>
    match parseAtom cs with
    | none => none
    | some (atom, rest) =>
      match parseQuant rest with
      | none => none
      | some (q, rest') =>
        match parsePieces rest' with
        | some (ps, tail) => some ({ atom, quant := q } :: ps, tail)
        | none => none

partial def parseAlts (cs : List Char) : Option (List Alt) :=
  match parsePieces cs with
  | none => none
  | some (ps, []) => some [{ pieces := ps }]
  | some (ps, '$' :: []) => some [{ pieces := ps, endAnchor := true }]
  | some (ps, '$' :: '|' :: rest) =>
    match parseAlts rest with
    | some more => some ({ pieces := ps, endAnchor := true } :: more)
    | none => none
  | some (ps, '|' :: rest) =>
    match parseAlts rest with
    | some more => some ({ pieces := ps } :: more)
    | none => none
  | _ => none

def parseRegex (pattern : String) : Option (List Alt) :=
  let cs := match pattern.toList with
    | '^' :: rest => rest
    | rest => rest
  parseAlts cs

partial def consumeExact (atom : Atom) (n : Nat) (cs : List Char) : Option (List Char) :=
  match n, cs with
  | 0, xs => some xs
  | n + 1, c :: xs => if matchAtom atom c then consumeExact atom n xs else none
  | _, [] => none

mutual
partial def matchPieces (ps : List Piece) (cs : List Char) (endAnchor : Bool) : Bool :=
  match ps with
  | [] => if endAnchor then cs.isEmpty else true
  | p :: rest =>
    match p.quant with
    | .one =>
      match cs with
      | [] => false
      | c :: cs' => matchAtom p.atom c && matchPieces rest cs' endAnchor
    | .exactly n =>
      match consumeExact p.atom n cs with
      | some xs => matchPieces rest xs endAnchor
      | none => false
    | .star => matchStar p.atom rest cs endAnchor
    | .plus =>
      match cs with
      | [] => false
      | c :: xs => matchAtom p.atom c && matchStar p.atom rest xs endAnchor

partial def matchStar (atom : Atom) (rest : List Piece) (cs : List Char) (endAnchor : Bool) : Bool :=
  matchPieces rest cs endAnchor ||
    match cs with
    | [] => false
    | c :: cs' => matchAtom atom c && matchStar atom rest cs' endAnchor
end

/-- Scoped regex match. Bad pattern → false (fail-closed). -/
def matchesRegex (pattern name : String) : Bool :=
  match parseRegex pattern with
  | none => false
  | some alts => alts.any (fun a => matchPieces a.pieces name.toList a.endAnchor)

def allowedRegex (patterns : List String) (name : String) : Bool :=
  patterns.any (fun p => matchesRegex p name)

def canConfigureRegex (p : Perms) (name : String) : Bool := allowedRegex p.configure name
def canPublishRegex (p : Perms) (name : String) : Bool := allowedRegex p.write name
def canReadRegex (p : Perms) (name : String) : Bool := allowedRegex p.read name

/-- Documented client profile rewritten as regex. -/
def replyPublishRestrictedClientRe : Perms :=
  { configure := ["^nr\\.reply\\."]
    write := ["^nr\\.mesh"]
    read := ["^nr\\.reply\\."] }

/-- Documented service profile rewritten as regex. -/
def replyPublishRestrictedServiceRe : Perms :=
  { configure := ["^nr\\.svc\\.", "^nr\\.reply\\."]
    write := ["^nr\\.mesh", "^nr\\.reply\\.", "^nr\\.dlx\\."]
    read := ["^nr\\.svc\\.", "^nr\\.mesh", "^nr\\.dlx\\."] }

def meshBindNamespacedRe (service : ServiceName) : Perms :=
  { configure := ["^" ++ service]
    write := ["^" ++ service, "^nr\\.mesh"]
    read := ["^" ++ service, "^nr\\.mesh"] }

/-- Narrower than prefix: hex suffix after `nr.reply.`. -/
def replyHex8 : String := "^nr\\.reply\\.[0-9a-f]{8}"

theorem forgeDenied :
    canPublish replyPublishRestrictedClient "nr.reply.victim" = false := by
  native_decide

theorem serviceCanReply :
    canPublish replyPublishRestrictedService "nr.reply.abc" = true := by
  native_decide

theorem clientCanDeclareReply :
    canConfigure replyPublishRestrictedClient "nr.reply.own" = true := by
  native_decide

theorem clientCannotForge :
    canPublish replyPublishRestrictedClient "nr.reply.victim" = false := by
  native_decide

theorem meshBind_ok_in_namespace :
    canConfigure (meshBindNamespaced "orders") "orders.ping" = true := by
  native_decide

theorem meshBind_foreign_refused :
    canConfigure (meshBindNamespaced "orders") "payments.charge" = false := by
  native_decide

theorem regex_agrees_client_forge :
    canPublishRegex replyPublishRestrictedClientRe "nr.reply.victim" =
      canPublish replyPublishRestrictedClient "nr.reply.victim" := by
  native_decide

theorem regex_agrees_client_declare :
    canConfigureRegex replyPublishRestrictedClientRe "nr.reply.ownid" =
      canConfigure replyPublishRestrictedClient "nr.reply.ownid" := by
  native_decide

theorem regex_agrees_client_mesh :
    canPublishRegex replyPublishRestrictedClientRe "nr.mesh" =
      canPublish replyPublishRestrictedClient "nr.mesh" := by
  native_decide

theorem regex_agrees_service_reply :
    canPublishRegex replyPublishRestrictedServiceRe "nr.reply.abc" =
      canPublish replyPublishRestrictedService "nr.reply.abc" := by
  native_decide

theorem regex_agrees_service_mesh_events :
    canPublishRegex replyPublishRestrictedServiceRe "nr.mesh.events" =
      canPublish replyPublishRestrictedService "nr.mesh.events" := by
  native_decide

theorem regex_agrees_mesh_bind_ok :
    canConfigureRegex (meshBindNamespacedRe "orders") "orders.ping" =
      canConfigure (meshBindNamespaced "orders") "orders.ping" := by
  native_decide

theorem regex_agrees_mesh_bind_foreign :
    canConfigureRegex (meshBindNamespacedRe "orders") "payments.charge" =
      canConfigure (meshBindNamespaced "orders") "payments.charge" := by
  native_decide

theorem regex_hex8_allows_hex_suffix :
    matchesRegex replyHex8 "nr.reply.abcd1234victim" = true := by
  native_decide

theorem regex_hex8_rejects_nonhex :
    matchesRegex replyHex8 "nr.reply.ZZZZzzzzvictim" = false := by
  native_decide

end NuropbRmq.Pattern.Acl
