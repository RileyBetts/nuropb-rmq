/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Pattern.Envelope
import NuropbRmq.Pattern.Errors
import NuropbRmq.Pattern.Claims
import NuropbRmq.Pattern.Jwt
import NuropbRMQ.Session

namespace NuropbRMQ

open NuropbRmq.Pattern.Envelope
open NuropbRmq.Pattern.Errors
open NuropbRmq.Protocol

structure RpcClient where
  session : Session

def RpcClient.request (cli : RpcClient) (target method : String) (params : Json := .obj [])
    (requestId : Option String := none) (exchange : String := "")
    (claimsToken : Option String := none) : IO Json := do
  let rid ← Session.register cli.session requestId
  let body := encodeRequest method params rid
  let mut headers : Table := []
  if let some tok := claimsToken then
    headers := [("nr.claims", .longstr tok), ("nr.claims_typ", .longstr "JWT")]
  let props : BasicProperties := {
    contentType := some "application/json"
    correlationId := some rid
    replyTo := ← cli.session.replyQueue.get
    headers
    deliveryMode := some 2
  }
  let c ← cli.session.conn.get
  Session.remember cli.session rid {
    exchange, routingKey := target, body, properties := props, mandatory := true
  }
  try
    basicPublish c cli.session.channelId body exchange target props (mandatory := true) (wantConfirm := true)
  catch e =>
    Session.forget cli.session rid
    throw e
  let msg ← Session.waitReply cli.session rid
  if msg.properties.correlationId != some rid then
    throw (IO.userError "INVALID_ENVELOPE")
  match decodeResponse msg.body with
  | .error _ => throw (IO.userError "INVALID_ENVELOPE")
  | .ok (.ok v) => return v
  | .ok (.err code msg _) => throw (IO.userError s!"{code}: {msg}")

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

structure RpcServer where
  conn : AmqpConnection
  queue : String
  channelId : Nat := 1
  auth : Option AuthConfig := none
  handler : String → Json → IO Json

def RpcServer.serveOnce (srv : RpcServer) (msg : IncomingMessage) : IO Unit := do
  let replyTo := msg.properties.replyTo
  let corr := msg.properties.correlationId
  let mut out : ByteArray := ByteArray.empty
  try
    match decodeRequest msg.body with
    | .error _ =>
      out := encodeError INVALID_ENVELOPE "invalid JSON-RPC body" corr (.obj [])
    | .ok (method, params, bodyId) =>
      let rid := corr.getD bodyId
      if let some a := srv.auth then
        let now := (← IO.monoMsNow) / 1000
        let token := AuthConfig.claimsToken msg.properties
        let unauthorized := encodeError UNAUTHORIZED "unauthorized" (some rid) (.obj [
          ("code_name", .str "UNAUTHORIZED"), ("retryable", .bool false)
        ])
        match AuthConfig.verify a method rid msg.properties now with
        | .authPublicSkip =>
          let result ← srv.handler method params
          out := encodeResult result rid
        | .authOk =>
          if (← AuthConfig.applyAuthorize a method params token) then
            let result ← srv.handler method params
            out := encodeResult result rid
          else
            out := unauthorized
        | .authReject =>
          out := unauthorized
      else
        let result ← srv.handler method params
        out := encodeResult result rid
  catch e =>
    out := encodeError SERVER_ERROR "internal error" corr (.obj [("code_name", .str "SERVER_ERROR")])
    let _ := e
  if let some rt := replyTo then
    if rt ≠ "" then
      let props : BasicProperties := {
        contentType := some "application/json"
        correlationId := corr
      }
      basicPublish srv.conn srv.channelId out "" rt props
  basicAck srv.conn srv.channelId msg.deliveryTag

partial def RpcServer.serve (srv : RpcServer) : IO Unit := do
  let msg ← receive srv.conn 60000
  RpcServer.serveOnce srv msg
  RpcServer.serve srv

end NuropbRMQ
