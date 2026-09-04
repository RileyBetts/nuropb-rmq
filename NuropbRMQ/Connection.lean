/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.ConnectionSM
import NuropbRmq.Protocol.Frame
import NuropbRmq.Protocol.Field
import NuropbRmq.Protocol.Methods
import NuropbRmq.Config.QueueProfile
import NuropbRMQ.Config
import NuropbRMQ.Socket

/-!
PLAIN AMQP 0-9-1 connection. Handshake and ops use proven `tryStep` / `legalSend`.
-/

namespace NuropbRMQ

open NuropbRmq.Protocol
open NuropbRmq.Protocol.Bytes
open NuropbRmq.Config

structure IncomingMessage where
  deliveryTag : Nat
  exchange : String
  routingKey : String
  body : ByteArray
  properties : BasicProperties
  redelivered : Bool
  consumerTag : String

structure ConnState where
  fd : UInt32
  sm : NuropbRmq.Protocol.State
  frameMax : Nat
  heartbeat : Nat
  buffer : ByteArray
  blocked : Bool
  lastPeerMs : Nat
  confirmEnabled : Bool
  nextConfirm : Nat
  closed : Bool

instance : Inhabited ConnState where
  default := {
    fd := 0
    sm := {}
    frameMax := 131072
    heartbeat := 60
    buffer := ByteArray.empty
    blocked := false
    lastPeerMs := 0
    confirmEnabled := false
    nextConfirm := 1
    closed := true
  }

structure AmqpConnection where
  config : ConnectionConfig
  st : IO.Ref ConnState

def throwIo (msg : String) : IO α :=
  throw (IO.userError msg)

def stepOrThrow (sm : NuropbRmq.Protocol.State) (e : Event) : IO NuropbRmq.Protocol.State := do
  match tryStep sm e with
  | some s => return s
  | none => throwIo s!"illegal AMQP event {repr e} in conn={repr sm.conn}"

def writeAll (fd : UInt32) (buf : ByteArray) : IO Unit :=
  Socket.send fd buf

partial def fillAtLeast (st : IO.Ref ConnState) (n : Nat) : IO Unit := do
  let s ← st.get
  if s.closed then throwIo "connection closed"
  if s.buffer.size ≥ n then return
  let ready ← Socket.poll s.fd 1000
  if !ready then
    fillAtLeast st n
    return
  let chunk ← Socket.recv s.fd 8192
  st.modify fun s => { s with buffer := s.buffer ++ chunk }
  fillAtLeast st n

def takeBytes (st : IO.Ref ConnState) (n : Nat) : IO ByteArray := do
  fillAtLeast st n
  let s ← st.get
  let out := s.buffer.extract 0 n
  st.set { s with buffer := s.buffer.extract n s.buffer.size }
  return out

def sendFrame (st : IO.Ref ConnState) (f : Frame) : IO Unit := do
  let s ← st.get
  match encodeFrame f s.frameMax with
  | none => throwIo "encodeFrame failed (frame_max)"
  | some raw => writeAll s.fd raw

def sendMethod (st : IO.Ref ConnState) (ch : Nat) (m : Method) : IO Unit := do
  match encodeMethod m with
  | none => throwIo s!"encodeMethod failed {m.classId}.{m.methodId}"
  | some payload => sendFrame st { kind := .method, channel := ch, payload }

partial def readFrame (st : IO.Ref ConnState) : IO Frame := do
  fillAtLeast st 7
  let s ← st.get
  match getU32be s.buffer 3 with
  | none => throwIo "incomplete frame header"
  | some (size, _) =>
    if !decodeAccepted size 0 s.frameMax defaultMaxTableDepth then
      throwIo "frame exceeds frame_max"
    fillAtLeast st (8 + size)
    let s ← st.get
    match decodeFrame s.buffer s.frameMax 0 with
    | none => throwIo "decodeFrame failed"
    | some (fr, next) =>
      st.set { s with buffer := s.buffer.extract next s.buffer.size, lastPeerMs := (← IO.monoMsNow) }
      return fr

partial def expectMethod (st : IO.Ref ConnState) (ch classId methodId : Nat) : IO Method := do
  let fr ← readFrame st
  if fr.kind == .heartbeat then
    expectMethod st ch classId methodId
  else if fr.kind != .method then
    throwIo "expected method frame"
  else
    match decodeMethod fr.payload with
    | none => throwIo "decodeMethod failed"
    | some m =>
      if m.classId == CONNECTION && m.methodId == CONNECTION_BLOCKED then
        st.modify fun s => { s with blocked := true, sm := (tryStep s.sm .blocked).getD s.sm }
        expectMethod st ch classId methodId
      else if m.classId == CONNECTION && m.methodId == CONNECTION_UNBLOCKED then
        st.modify fun s => { s with blocked := false, sm := (tryStep s.sm .unblocked).getD s.sm }
        expectMethod st ch classId methodId
      else if m.classId == CONNECTION && m.methodId == CONNECTION_CLOSE then
        let _ ← sendMethod st 0 { classId := CONNECTION, methodId := CONNECTION_CLOSE_OK }
        throwIo s!"broker closed: {argStr m.args "reply_text"}"
      else if m.classId == CHANNEL && m.methodId == CHANNEL_CLOSE then
        throwIo s!"channel.close {argInt m.args "reply_code"} {argStr m.args "reply_text"}"
      else if fr.channel == ch && m.classId == classId && m.methodId == methodId then
        return m
      else
        throwIo s!"unexpected method {m.classId}.{m.methodId} ch={fr.channel}"

def connect (cfg : ConnectionConfig := {}) : IO AmqpConnection := do
  if cfg.heartbeat = 0 ∨ cfg.heartbeat > 60 then
    throwIo s!"heartbeat must be 1..60, got {cfg.heartbeat}"
  if cfg.tls then
    throwIo "TLS requires NuropbRMQTls (not default lake target)"
  let fd ← Socket.connect cfg.host cfg.port
  let mut sm : NuropbRmq.Protocol.State := {}
  sm ← stepOrThrow sm (.tcpConnected false)
  sm ← stepOrThrow sm .amqpHeader
  writeAll fd protocolHeader
  let st ← IO.mkRef {
    fd, sm, frameMax := cfg.frameMax, heartbeat := cfg.heartbeat
    buffer := ByteArray.empty, blocked := false
    lastPeerMs := (← IO.monoMsNow)
    confirmEnabled := false, nextConfirm := 1, closed := false
  }
  let start ← expectMethod st 0 CONNECTION CONNECTION_START
  sm ← stepOrThrow (← st.get).sm .connStart
  let mechanisms := argStr start.args "mechanisms"
  if !(mechanisms.splitOn " ").contains "PLAIN" then
    throwIo s!"PLAIN not offered: {mechanisms}"
  let response := (ByteArray.empty.push 0) ++ cfg.username.toUTF8 ++ (ByteArray.empty.push 0) ++ cfg.password.toUTF8
  if !legalSend .startOk sm.conn then throwIo "illegal start-ok"
  sendMethod st 0 {
    classId := CONNECTION, methodId := CONNECTION_START_OK
    args := [
      ("client_properties", .table [("product", .longstr "nuropb-rmq"), ("version", .longstr "lean-0.1")]),
      ("mechanism", .longstr "PLAIN"),
      ("response", .bytes response),
      ("locale", .longstr "en_US"),
    ]
  }
  sm ← stepOrThrow sm .startOk
  let tune ← expectMethod st 0 CONNECTION CONNECTION_TUNE
  sm ← stepOrThrow sm .tune
  let frameMax :=
    let fm := (argInt tune.args "frame_max").toNat
    if fm == 0 then cfg.frameMax else min fm cfg.frameMax
  let hb := min (min (argInt tune.args "heartbeat").toNat cfg.heartbeat) 60
  let hb := if hb == 0 then cfg.heartbeat else hb
  if !legalSend .tuneOk sm.conn then throwIo "illegal tune-ok"
  sendMethod st 0 {
    classId := CONNECTION, methodId := CONNECTION_TUNE_OK
    args := [("channel_max", .int 2047), ("frame_max", .int frameMax), ("heartbeat", .int hb)]
  }
  sm ← stepOrThrow sm (.tuneOk hb)
  sendMethod st 0 {
    classId := CONNECTION, methodId := CONNECTION_OPEN
    args := [("virtual_host", .longstr cfg.virtualHost)]
  }
  sm ← stepOrThrow sm .open
  let _ ← expectMethod st 0 CONNECTION CONNECTION_OPEN_OK
  sm ← stepOrThrow sm .openOk
  st.modify fun s => { s with sm, frameMax, heartbeat := hb }
  return { config := cfg, st }

def close (c : AmqpConnection) : IO Unit := do
  let s ← c.st.get
  if s.closed then return
  if !s.sm.conn.isTerminal then
    try
      let sm ← stepOrThrow s.sm .beginClose
      c.st.modify fun x => { x with sm }
      let closeArgs : Table := [("reply_code", .int 200), ("reply_text", .longstr "")]
      sendMethod c.st 0 { classId := CONNECTION, methodId := 50, args := closeArgs }
      let _ ← expectMethod c.st 0 CONNECTION 51
      let cur ← c.st.get
      let sm' := (tryStep cur.sm .closeOk).getD cur.sm
      c.st.modify fun x => { x with sm := sm' }
    catch _ =>
      pure ()
  let s ← c.st.get
  Socket.close s.fd
  c.st.modify fun x => { x with closed := true }

def openChannel (c : AmqpConnection) (channelId : Nat := 1) : IO Nat := do
  let s ← c.st.get
  let sm ← stepOrThrow s.sm .chanOpen
  c.st.set { s with sm }
  sendMethod c.st channelId { classId := CHANNEL, methodId := CHANNEL_OPEN }
  let _ ← expectMethod c.st channelId CHANNEL CHANNEL_OPEN_OK
  let s ← c.st.get
  let sm ← stepOrThrow s.sm .chanOpenOk
  c.st.set { s with sm }
  return channelId

def confirmSelect (c : AmqpConnection) (channelId : Nat) : IO Unit := do
  let s ← c.st.get
  if s.confirmEnabled then return
  sendMethod c.st channelId { classId := CONFIRM, methodId := CONFIRM_SELECT }
  let _ ← expectMethod c.st channelId CONFIRM CONFIRM_SELECT_OK
  c.st.modify fun x => { x with confirmEnabled := true }

def exchangeDeclare (c : AmqpConnection) (channelId : Nat) (exchange type_ : String)
    (durable autoDelete : Bool := false) : IO Unit := do
  sendMethod c.st channelId {
    classId := EXCHANGE, methodId := EXCHANGE_DECLARE
    args := [
      ("exchange", .longstr exchange), ("type", .longstr type_),
      ("durable", .bool durable), ("auto_delete", .bool autoDelete),
    ]
  }
  let _ ← expectMethod c.st channelId EXCHANGE EXCHANGE_DECLARE_OK

def queueDeclare (c : AmqpConnection) (channelId : Nat) (queue : String)
    (durable exclusive autoDelete : Bool := false) (arguments : Table := []) : IO String := do
  sendMethod c.st channelId {
    classId := QUEUE, methodId := QUEUE_DECLARE
    args := [
      ("queue", .longstr queue), ("durable", .bool durable),
      ("exclusive", .bool exclusive), ("auto_delete", .bool autoDelete),
      ("arguments", .table arguments),
    ]
  }
  let ok ← expectMethod c.st channelId QUEUE QUEUE_DECLARE_OK
  return argStr ok.args "queue"

def queueBind (c : AmqpConnection) (channelId : Nat) (queue exchange routingKey : String) : IO Unit := do
  sendMethod c.st channelId {
    classId := QUEUE, methodId := QUEUE_BIND
    args := [
      ("queue", .longstr queue), ("exchange", .longstr exchange),
      ("routing_key", .longstr routingKey),
    ]
  }
  let _ ← expectMethod c.st channelId QUEUE QUEUE_BIND_OK

def profileArgs (p : QueueProfile) (name : String) (dlx : Option String) (ttl : Option Nat)
    (queueType : String := "classic") (dlrk : Option String := none)
    (deliveryLimit : Option Nat := none) : Table :=
  let t : Table := []
  let t := if queueType == "quorum" then t ++ [("x-queue-type", .longstr "quorum")] else t
  let t := match ttl with | some ms => t ++ [("x-message-ttl", .int ms)] | none => t
  let t := match dlx with
    | some x => t ++ [("x-dead-letter-exchange", .longstr x)]
    | none => t
  let t := match dlrk with
    | some k => t ++ [("x-dead-letter-routing-key", .longstr k)]
    | none => t
  let t := match deliveryLimit with
    | some n => t ++ [("x-delivery-limit", .int n)]
    | none => t
  let _ := (p, name)
  t

def queueDeclareProfile (c : AmqpConnection) (channelId : Nat) (queue : String)
    (durable : Bool := true) (exclusive autoDelete : Bool := false)
    (dlx : Option String := none) (ttlMs : Option Nat := none)
    (queueType : String := "classic") (dlrk : Option String := none)
    (deliveryLimit : Option Nat := none) : IO String := do
  if queueType == "quorum" && (exclusive || autoDelete) then
    throwIo "quorum queues cannot be exclusive or auto-delete"
  if let some x := dlx then
    exchangeDeclare c channelId x "topic" (durable := true)
  queueDeclare c channelId queue durable exclusive autoDelete
    (profileArgs durableAtLeastOnce queue dlx ttlMs queueType dlrk deliveryLimit)

def basicPublish (c : AmqpConnection) (channelId : Nat) (body : ByteArray)
    (exchange routingKey : String := "") (props : BasicProperties := {})
    (mandatory : Bool := false) (wantConfirm : Bool := false) : IO Unit := do
  let s ← c.st.get
  if s.blocked || !publishAllowed s.sm then
    throwIo "connection.blocked — publish refused"
  if wantConfirm && !s.confirmEnabled then
    confirmSelect c channelId
  sendMethod c.st channelId {
    classId := BASIC, methodId := BASIC_PUBLISH
    args := [
      ("exchange", .longstr exchange), ("routing_key", .longstr routingKey),
      ("mandatory", .bool mandatory),
    ]
  }
  match encodeContentHeader BASIC body.size props with
  | none => throwIo "encodeContentHeader failed"
  | some header =>
    sendFrame c.st { kind := .header, channel := channelId, payload := header }
    let payloadMax := (maxFramePayload s.frameMax).getD 131064
    if body.size == 0 then
      sendFrame c.st { kind := .body, channel := channelId, payload := ByteArray.empty }
    else
      let mut off := 0
      while off < body.size do
        let n := min payloadMax (body.size - off)
        sendFrame c.st { kind := .body, channel := channelId, payload := body.extract off (off + n) }
        off := off + n
  if wantConfirm || (← c.st.get).confirmEnabled then
    let _ ← expectMethod c.st channelId BASIC BASIC_ACK

def basicConsume (c : AmqpConnection) (channelId : Nat) (queue : String) : IO String := do
  sendMethod c.st channelId {
    classId := BASIC, methodId := BASIC_CONSUME
    args := [("queue", .longstr queue)]
  }
  let ok ← expectMethod c.st channelId BASIC BASIC_CONSUME_OK
  return argStr ok.args "consumer_tag"

def basicAck (c : AmqpConnection) (channelId deliveryTag : Nat) : IO Unit :=
  sendMethod c.st channelId {
    classId := BASIC, methodId := BASIC_ACK
    args := [("delivery_tag", .int deliveryTag)]
  }

def basicNack (c : AmqpConnection) (channelId deliveryTag : Nat) (requeue : Bool := false) : IO Unit :=
  sendMethod c.st channelId {
    classId := BASIC, methodId := BASIC_NACK
    args := [("delivery_tag", .int deliveryTag), ("requeue", .bool requeue)]
  }

partial def assembleContent (c : AmqpConnection) (channelId : Nat) : IO (BasicProperties × ByteArray) := do
  let fr ← readFrame c.st
  if fr.kind == .heartbeat then assembleContent c channelId
  else if fr.kind != .header || fr.channel != channelId then
    throwIo "expected content header"
  else
    match decodeContentHeader fr.payload with
    | none => throwIo "decodeContentHeader failed"
    | some (_, bodySize, props) =>
      let mut body := ByteArray.empty
      while body.size < bodySize do
        let bf ← readFrame c.st
        if bf.kind == .heartbeat then continue
        if bf.kind != .body then throwIo "expected body frame"
        body := body ++ bf.payload
      return (props, body)

partial def receive (c : AmqpConnection) (timeoutMs : Nat := 30000) : IO IncomingMessage := do
  let s ← c.st.get
  -- Deliver may already be buffered (same TCP read as consume-ok / prior frame).
  if s.buffer.isEmpty then
    let ready ← Socket.poll s.fd timeoutMs.toUInt32
    if !ready then throwIo "receive timeout"
  let fr ← readFrame c.st
  if fr.kind == .heartbeat then
    receive c timeoutMs
  else if fr.kind != .method then
    throwIo "expected method (deliver/return)"
  else
    match decodeMethod fr.payload with
    | none => throwIo "decodeMethod failed"
    | some m =>
      if m.classId == CONNECTION && m.methodId == CONNECTION_BLOCKED then
        c.st.modify fun x => { x with blocked := true }
        receive c timeoutMs
      else if m.classId == BASIC && m.methodId == BASIC_RETURN then
        let _ ← assembleContent c fr.channel
        throwIo s!"basic.return {argInt m.args "reply_code"} {argStr m.args "reply_text"}"
      else if m.classId == BASIC && m.methodId == BASIC_DELIVER then
        let (props, body) ← assembleContent c fr.channel
        return {
          deliveryTag := (argInt m.args "delivery_tag").toNat
          exchange := argStr m.args "exchange"
          routingKey := argStr m.args "routing_key"
          body, properties := props
          redelivered := argBool m.args "redelivered"
          consumerTag := argStr m.args "consumer_tag"
        }
      else if m.classId == BASIC && m.methodId == BASIC_ACK then
        receive c timeoutMs
      else
        throwIo s!"unexpected inbound {m.classId}.{m.methodId}"

def updateSecret (c : AmqpConnection) (newSecret reason : String) : IO Unit := do
  let s ← c.st.get
  if !legalSend .updateSecret s.sm.conn then throwIo "illegal update-secret"
  sendMethod c.st 0 {
    classId := CONNECTION, methodId := CONNECTION_UPDATE_SECRET
    args := [("new_secret", .longstr newSecret), ("reason", .longstr reason)]
  }
  let _ ← expectMethod c.st 0 CONNECTION CONNECTION_UPDATE_SECRET_OK
  let sm ← stepOrThrow s.sm .updateSecret
  c.st.modify fun x => { x with sm }

end NuropbRMQ
