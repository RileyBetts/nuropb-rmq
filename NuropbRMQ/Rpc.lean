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

structure AuthConfig where
  jwtSecret : String
  publicMethods : List String := []
  deriving Repr

def AuthConfig.verify (a : AuthConfig) (method corrId : String) (props : BasicProperties)
    (now : Nat) : NuropbRmq.Pattern.Claims.AuthOutcome :=
  let isPublic := a.publicMethods.contains method
  let token :=
    match NuropbRmq.Protocol.tableGetStr props.headers "nr.claims" with
    | some t => t
    | none => ""
  NuropbRmq.Pattern.Jwt.verifyHs256 a.jwtSecret token now corrId method isPublic

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
        match AuthConfig.verify a method rid msg.properties now with
        | .authOk | .authPublicSkip =>
          let result ← srv.handler method params
          out := encodeResult result rid
        | .authReject =>
          out := encodeError UNAUTHORIZED "unauthorized" (some rid) (.obj [
            ("code_name", .str "UNAUTHORIZED"), ("retryable", .bool false)
          ])
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
