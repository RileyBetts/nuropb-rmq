/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Envelope
import NuropbRmq.Pattern.Errors
import NuropbRmq.Pattern.Claims
import NuropbRmq.Pattern.Jwt
import Std.Async
import NuropbRmq.Session.Dedup
import NuropbRMQ.Session

namespace NuropbRMQ

open Std.Async

open NuropbRmq.Pattern.Envelope
open NuropbRmq.Pattern.Errors
open NuropbRmq.Protocol

structure RpcClient where
  session : Session

def RpcClient.requestAsync (cli : RpcClient) (target method : String) (params : Json := .obj [])
    (requestId : Option String := none) (exchange : String := "")
    (claimsToken : Option String := none) : Async Json := do
  let (rid, c, replyTo) ← ioRun do
    let rid ← Session.register cli.session requestId
    let (c, q) ← Session.rpcHandles cli.session
    return (rid, c, some q)
  let body := encodeRequest method params rid
  let mut headers : Table := []
  if let some tok := claimsToken then
    headers := [("nr.claims", .longstr tok), ("nr.claims_typ", .longstr "JWT")]
  let props : BasicProperties := {
    contentType := some "application/json"
    correlationId := some rid
    replyTo
    headers
    deliveryMode := some 2
  }
  unless cli.session.policy.failOutstanding do
    ioRun (Session.remember cli.session rid {
      exchange, routingKey := target, body, properties := props, mandatory := true
    })
  try
    let confirmP ← basicPublishKickAsync c cli.session.channelId body exchange target props
      (mandatory := true) (wantConfirm := true)
    let replyJob := waitReplyWaiterAsync c.st rid
    let msg ←
      match confirmP with
      | some p => do
        let (_conf, m) ← Async.concurrently (awaitExceptAsync p) replyJob
        pure m
      | none => replyJob
    basicAckAsync c cli.session.channelId msg.deliveryTag
    ioRun (Session.forget cli.session rid)
    if msg.properties.correlationId != some rid then
      throw (IO.userError "INVALID_ENVELOPE")
    match decodeResponse msg.body with
    | .error _ => throw (IO.userError "INVALID_ENVELOPE")
    | .ok (.ok v) => return v
    | .ok (.err code msg _) => throw (IO.userError s!"{code}: {msg}")
  catch e =>
    ioRun (Session.forget cli.session rid)
    throw e

def RpcClient.request (cli : RpcClient) (target method : String) (params : Json := .obj [])
    (requestId : Option String := none) (exchange : String := "")
    (claimsToken : Option String := none) : Async Json :=
  RpcClient.requestAsync cli target method params requestId exchange claimsToken

/-- N in-flight RPCs on one session (one UV loop; no nested `.block`). -/
def RpcClient.requestAll (cli : RpcClient) (reqs : List (String × String × Json))
    (exchange : String := "") : Async (List Json) := do
  let jobs := reqs.toArray.map fun (target, method, params) =>
    RpcClient.requestAsync cli target method params (exchange := exchange)
  let rs ← Async.concurrentlyAll jobs
  return rs.toList

/-- Lean counterpart of Python `AuthConfig`. The optional hook runs only after
HS256 (later RS/ES) succeeds. `none` is allow (`authorizeOk = true`). -/
structure AuthConfig where
  jwtSecret : String
  publicMethods : List String := []
  authorize : Option (String → String → Json → IO Bool) := none

def AuthConfig.claimsToken (props : BasicProperties) : String :=
  match NuropbRmq.Protocol.tableGetStr props.headers "nr.claims" with
  | some t => t
  | none => ""

def AuthConfig.verify (a : AuthConfig) (method corrId : String) (props : BasicProperties)
    (now : Nat) : NuropbRmq.Pattern.Claims.AuthOutcome :=
  let isPublic := a.publicMethods.contains method
  let token := AuthConfig.claimsToken props
  NuropbRmq.Pattern.Jwt.verifyHs256 a.jwtSecret token now corrId method isPublic

/-- Python `authorize_func`: exception or `false` → deny. Public skip does not call this. -/
def AuthConfig.applyAuthorize (a : AuthConfig) (method : String) (params : Json)
    (token : String) : IO Bool := do
  match a.authorize with
  | none => return true
  | some f =>
    try
      let claims := (NuropbRmq.Pattern.Jwt.payloadJson token).getD ""
      f claims method params
    catch _ =>
      return false

structure DedupState where
  cap : Nat
  seen : List String := []
  cache : List (String × Json) := []

def DedupState.lookup (st : DedupState) (rid : String) : Option Json :=
  (st.cache.find? (fun p => p.1 == rid)).map (·.2)

def DedupState.store (st : DedupState) (rid : String) (result : Json) : DedupState :=
  let (_, seen') := NuropbRmq.Session.tryDedup st.seen st.cap rid
  { st with
    seen := seen'
    cache := (rid, result) :: st.cache |>.filter (fun p => seen'.contains p.1) }

/-- Decode + auth + optional dedup. No broker I/O (used by serveOnce and the smoke). -/
def handleRpc
    (handler : String → Json → IO Json)
    (auth : Option AuthConfig)
    (dedup : Option (IO.Ref DedupState))
    (msg : IncomingMessage) : IO ByteArray := do
  let corr := msg.properties.correlationId
  try
    match decodeRequest msg.body with
    | .error _ =>
      return encodeError INVALID_ENVELOPE "invalid JSON-RPC body" corr (.obj [])
    | .ok (method, params, bodyId) =>
      let rid := corr.getD bodyId
      let runHandler : IO ByteArray := do
        match dedup with
        | some ref =>
          let st ← ref.get
          match st.lookup rid with
          | some cached =>
            return encodeResult cached rid
          | none =>
            let result ← handler method params
            ref.set (st.store rid result)
            return encodeResult result rid
        | none =>
          let result ← handler method params
          return encodeResult result rid
      if let some a := auth then
        let now := (← IO.monoMsNow) / 1000
        let token := AuthConfig.claimsToken msg.properties
        let unauthorized := encodeError UNAUTHORIZED "unauthorized" (some rid) (.obj [
          ("code_name", .str "UNAUTHORIZED"), ("retryable", .bool false)
        ])
        match AuthConfig.verify a method rid msg.properties now with
        | .authPublicSkip => runHandler
        | .authOk =>
          if (← AuthConfig.applyAuthorize a method params token) then
            runHandler
          else
            return unauthorized
        | .authReject => return unauthorized
      else
        runHandler
  catch _ =>
    return encodeError SERVER_ERROR "internal error" corr (.obj [("code_name", .str "SERVER_ERROR")])

structure RpcServer where
  conn : AmqpConnection
  queue : String
  channelId : Nat := 1
  auth : Option AuthConfig := none
  handler : String → Json → IO Json
  dedup : Option (IO.Ref DedupState) := none

def RpcServer.serveOnceAsync (srv : RpcServer) (msg : IncomingMessage) : Async Unit := do
  let replyTo := msg.properties.replyTo
  let corr := msg.properties.correlationId
  let out ← ioRun (handleRpc srv.handler srv.auth srv.dedup msg)
  if let some rt := replyTo then
    if rt ≠ "" then
      let props : BasicProperties := {
        contentType := some "application/json"
        correlationId := corr
      }
      publishAndAckAsync srv.conn srv.channelId out "" rt props msg.deliveryTag
    else
      basicAckAsync srv.conn srv.channelId msg.deliveryTag
  else
    basicAckAsync srv.conn srv.channelId msg.deliveryTag

def RpcServer.serveOnce (srv : RpcServer) (msg : IncomingMessage) : Async Unit :=
  RpcServer.serveOnceAsync srv msg

partial def RpcServer.serveAsync (srv : RpcServer) : Async Unit := do
  let msg ← receiveAsync srv.conn 60000
  RpcServer.serveOnceAsync srv msg
  RpcServer.serveAsync srv

partial def RpcServer.serve (srv : RpcServer) : Async Unit :=
  RpcServer.serveAsync srv

end NuropbRMQ
