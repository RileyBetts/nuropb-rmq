/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Mesh

/-!
Executable nuropb ACL profiles (not RabbitMQ's regex engine).

`reply-publish-restricted`: services may write `nr.reply.*`; clients must not
(forge denied). `mesh-bind-namespaced`: configure only under the service prefix;
`tryBind` is the client-side subset of that gate.
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

end NuropbRmq.Pattern.Acl
