/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.ConnectionSM
import NuropbRmq.Protocol.Frame
import NuropbRmq.Protocol.Field
import NuropbRmq.Protocol.Methods
import NuropbRmq.Config.QueueProfile
import Std.Async
import Std.Async.Timer
import Std.Data.HashMap
import NuropbRMQ.Config
import NuropbRMQ.Socket
import NuropbRMQ.Transport
import NuropbRMQ.AsyncTransport

/-!
PLAIN AMQP 0-9-1 connection. Handshake and ops use proven `tryStep` / `legalSend`.
Sockets are `Std.Async.TCP` (libuv). After OPEN_OK a background pump demuxes
frames into waiters (Python `_read_loop`). Public APIs are `Async`. AMQPS
supplies an `AsyncByteTransport` from `NuropbRMQTls` (memory BIO / `WANT_*`).
-/

namespace NuropbRMQ

open NuropbRmq.Protocol
open NuropbRmq.Protocol.Bytes
open NuropbRmq.Config
open Std.Async

structure IncomingMessage where
  deliveryTag : Nat
  exchange : String
  routingKey : String
  body : ByteArray
  properties : BasicProperties
  redelivered : Bool
  consumerTag : String

instance : Inhabited IncomingMessage where
  default := {
    deliveryTag := 0
    exchange := ""
    routingKey := ""
    body := ByteArray.empty
    properties := {}
    redelivered := false
    consumerTag := ""
  }

/-- Method waiter: first match on channel + class + method. -/
structure MethodWaiter where
  ch : Nat
  classId : Nat
  methodId : Nat
  promise : IO.Promise (Except IO.Error Method)

structure ConnState where
  fd : UInt32
  io : Transport
  aio : AsyncByteTransport := default
  sm : NuropbRmq.Protocol.State
  frameMax : Nat
  heartbeat : Nat
  buffer : ByteArray
  bufOff : Nat := 0
  blocked : Bool
  lastPeerMs : Nat
  confirmEnabled : Bool
  nextConfirm : Nat
  closed : Bool
  inbox : List IncomingMessage
  pumped : Bool := false
  lost : Option String := none
  methodWaiters : List MethodWaiter := []
  confirmWaiters : Std.HashMap Nat (IO.Promise (Except IO.Error Unit)) := {}
  deliverWaiters : List (IO.Promise (Except IO.Error IncomingMessage)) := []
  replyWaiters : Std.HashMap String (IO.Promise (Except IO.Error IncomingMessage)) := {}
  writeBusy : Bool := false
  writeWaiters : List (IO.Promise (Except IO.Error Unit)) := []
  writePending : List ByteArray := []
  writeFlushing : Bool := false

def recvChunk : Nat := 65536

def ConnState.avail (s : ConnState) : Nat :=
  s.buffer.size - s.bufOff

def ConnState.compact (s : ConnState) : ConnState :=
  if s.bufOff == 0 then s
  else { s with buffer := s.buffer.extract s.bufOff s.buffer.size, bufOff := 0 }

/-- Drop the dead prefix only when it is large relative to remaining bytes. -/
def ConnState.compactIfNeeded (s : ConnState) : ConnState :=
  if s.bufOff > 0 && s.bufOff * 2 ≥ s.buffer.size then s.compact else s

instance : Inhabited ConnState where
  default := {
    fd := 0
    io := default
    aio := default
    sm := {}
    frameMax := 131072
    heartbeat := 60
    buffer := ByteArray.empty
    blocked := false
    lastPeerMs := 0
    confirmEnabled := false
    nextConfirm := 1
    closed := true
    inbox := []
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

def awaitExceptAsync (p : IO.Promise (Except IO.Error α)) : Async α :=
  Async.ofPromise (pure p)

def getSt (st : IO.Ref ConnState) : Async ConnState :=
  liftM (st.get : IO ConnState)

def modSt (st : IO.Ref ConnState) (f : ConnState → ConnState) : Async Unit :=
  liftM (st.modify f : IO Unit)

def setSt (st : IO.Ref ConnState) (s : ConnState) : Async Unit :=
  liftM (st.set s : IO Unit)

def ioRun (act : IO α) : Async α :=
  liftM act

/-- Async-safe write lock (promise queue). Do not use a blocking mutex on the UV thread. -/
def acquireWrite (st : IO.Ref ConnState) : Async Unit := do
  let p ← IO.Promise.new
  let immediate ← ioRun (st.modifyGet fun s =>
    if !s.writeBusy && s.writeWaiters.isEmpty then
      (true, { s with writeBusy := true })
    else
      (false, { s with writeBusy := true, writeWaiters := s.writeWaiters ++ [p] }))
  unless immediate do
    awaitExceptAsync p

def releaseWrite (st : IO.Ref ConnState) : Async Unit := do
  let nxt ← ioRun (st.modifyGet fun s =>
    match s.writeWaiters with
    | p :: rest => (some p, { s with writeWaiters := rest })
    | [] => (none, { s with writeBusy := false }))
  match nxt with
  | some p => ioRun (p.resolve (.ok ()))
  | none => pure ()

def failWaiters (st : IO.Ref ConnState) (msg : String) : IO Unit := do
  let s ← st.get
  let err : IO.Error := IO.userError msg
  for w in s.methodWaiters do
    w.promise.resolve (.error err)
  for (_, p) in s.confirmWaiters.toList do
    p.resolve (.error err)
  for p in s.deliverWaiters do
    p.resolve (.error err)
  for (_, p) in s.replyWaiters.toList do
    p.resolve (.error err)
  for p in s.writeWaiters do
    p.resolve (.error err)
  st.modify fun x => {
    x with
    lost := some msg
    closed := true
    methodWaiters := []
    confirmWaiters := {}
    deliverWaiters := []
    replyWaiters := {}
    writeBusy := false
    writeWaiters := []
    writePending := []
    writeFlushing := false
  }

def concatBytes (xs : List ByteArray) : ByteArray :=
  match xs with
  | [] => ByteArray.empty
  | [x] => x
  | _ =>
    let sz := xs.foldl (init := 0) (fun acc b => acc + b.size)
    xs.foldl (init := ByteArray.emptyWithCapacity sz) (fun acc b => acc ++ b)

/-- Drain `writePending` into one `aio.send`. Complete bursts only (no mid-frame splice). -/
partial def flushWrites (st : IO.Ref ConnState) : Async Unit := do
  let chunks ← ioRun (st.modifyGet fun s =>
    (s.writePending, { s with writePending := [] }))
  if chunks.isEmpty then
    let again ← ioRun (st.modifyGet fun s =>
      if s.writePending.isEmpty then
        (false, { s with writeFlushing := false })
      else
        (true, s))
    if again then flushWrites st
    return
  let s ← getSt st
  if s.closed then return
  try
    s.aio.send (concatBytes chunks)
  catch e =>
    ioRun (failWaiters st (toString e))
    throw e
  flushWrites st

/-- Enqueue a complete AMQP burst and kick the flusher if idle. -/
def sendRawAsync (st : IO.Ref ConnState) (raw : ByteArray) : Async Unit := do
  let kick ← ioRun (st.modifyGet fun s =>
    if s.closed then
      (none, s)
    else
      let s := { s with writePending := s.writePending ++ [raw] }
      if s.writeFlushing then
        (some false, s)
      else
        (some true, { s with writeFlushing := true }))
  match kick with
  | none => throw (IO.userError "connection closed")
  | some true => flushWrites st
  | some false => pure ()

/-- Resolve the oldest waiter matching this (ch, class, method). -/
def resolveMethod1 (st : IO.Ref ConnState) (ch : Nat) (m : Method) : IO Bool := do
  let s ← st.get
  let rec go (xs acc : List MethodWaiter) : IO Bool := do
    match xs with
    | [] =>
      st.modify fun x => { x with methodWaiters := acc.reverse }
      return false
    | w :: rest =>
      if w.ch == ch && w.classId == m.classId && w.methodId == m.methodId then
        w.promise.resolve (.ok m)
        st.modify fun x => { x with methodWaiters := acc.reverse ++ rest }
        return true
      else
        go rest (w :: acc)
  go s.methodWaiters []

def resolveConfirm (st : IO.Ref ConnState) (tag : Nat) (multiple : Bool) : IO Unit := do
  let s ← st.get
  if multiple then
    let mut keep := s.confirmWaiters
    for (t, p) in s.confirmWaiters.toList do
      if t ≤ tag then
        p.resolve (.ok ())
        keep := keep.erase t
    st.modify fun x => { x with confirmWaiters := keep }
  else
    match s.confirmWaiters.get? tag with
    | some p =>
      p.resolve (.ok ())
      st.modify fun x => { x with confirmWaiters := x.confirmWaiters.erase tag }
    | none => pure ()

def offerDeliver (st : IO.Ref ConnState) (msg : IncomingMessage) : IO Unit := do
  let rid := msg.properties.correlationId
  let hit ← st.modifyGet fun s =>
    match rid with
    | some id =>
      match s.replyWaiters.get? id with
      | some p =>
        (some p, { s with replyWaiters := s.replyWaiters.erase id })
      | none =>
        match s.deliverWaiters with
        | p :: rest => (some p, { s with deliverWaiters := rest })
        | [] => (none, { s with inbox := s.inbox ++ [msg] })
    | none =>
      match s.deliverWaiters with
      | p :: rest => (some p, { s with deliverWaiters := rest })
      | [] => (none, { s with inbox := s.inbox ++ [msg] })
  match hit with
  | some p => p.resolve (.ok msg)
  | none => pure ()

def sendFrameAsync (st : IO.Ref ConnState) (f : Frame) : Async Unit := do
  let s ← getSt st
  match encodeFrame f s.frameMax with
  | none => throw (IO.userError "encodeFrame failed (frame_max)")
  | some raw =>
    if s.pumped then
      sendRawAsync st raw
    else
      s.aio.send raw

def sendMethodAsync (st : IO.Ref ConnState) (ch : Nat) (m : Method) : Async Unit := do
  match encodeMethod m with
  | none => throw (IO.userError s!"encodeMethod failed {m.classId}.{m.methodId}")
  | some payload => sendFrameAsync st { kind := .method, channel := ch, payload }

/-- One AMQP method+content: one encode + one `aio.send` (Python coalesce + `_drain`). -/
def sendBurstAsync (st : IO.Ref ConnState) (frames : List Frame) : Async Unit := do
  let s0 ← getSt st
  match encodeBurst frames s0.frameMax with
  | none => throw (IO.userError "encodeBurst failed (frame_max)")
  | some raw =>
    if s0.pumped then
      sendRawAsync st raw
    else
      s0.aio.send raw

partial def fillAtLeastAio (st : IO.Ref ConnState) (n : Nat) : Async Unit := do
  let s ← getSt st
  if s.closed then throw (IO.userError (s.lost.getD "connection closed"))
  if s.avail ≥ n then return
  if s.bufOff > 0 then
    modSt st fun x => x.compact
  let s ← getSt st
  match ← s.aio.recv? recvChunk with
  | none =>
    ioRun (failWaiters st "connection closed")
    throw (IO.userError "connection closed")
  | some chunk =>
    -- Watchdog timestamp is updated on heartbeat / idle, not every socket read.
    modSt st fun x => { x with buffer := x.buffer ++ chunk }
    fillAtLeastAio st n

partial def readFrameAio (st : IO.Ref ConnState) : Async Frame := do
  fillAtLeastAio st 7
  let s ← getSt st
  match getU32be s.buffer (s.bufOff + 3) with
  | none => throw (IO.userError "incomplete frame header")
  | some (size, _) =>
    if !decodeAccepted size 0 s.frameMax defaultMaxTableDepth then
      throw (IO.userError "frame exceeds frame_max")
    fillAtLeastAio st (8 + size)
    let s ← getSt st
    match decodeFrame s.buffer s.frameMax s.bufOff with
    | none => throw (IO.userError "decodeFrame failed")
    | some (fr, next) =>
      -- `modify` so concurrent waiter registration is not wiped by a stale snapshot.
      modSt st fun x =>
        ({ x with bufOff := next }).compactIfNeeded
      return fr

partial def assembleContentAio (st : IO.Ref ConnState) (channelId : Nat) : Async (BasicProperties × ByteArray) := do
  let fr ← readFrameAio st
  if fr.kind == .heartbeat then assembleContentAio st channelId
  else if fr.kind != .header || fr.channel != channelId then
    throw (IO.userError "expected content header")
  else
    match decodeContentHeader fr.payload with
    | none => throw (IO.userError "decodeContentHeader failed")
    | some (_, bodySize, props) =>
      if bodySize == 0 then
        return (props, ByteArray.empty)
      let mut body := ByteArray.emptyWithCapacity bodySize
      while body.size < bodySize do
        let bf ← readFrameAio st
        if bf.kind == .heartbeat then continue
        if bf.kind != .body then throw (IO.userError "expected body frame")
        if body.size == 0 && bf.payload.size == bodySize then
          return (props, bf.payload)
        body := body ++ bf.payload
      return (props, body)

def dispatchMethod (st : IO.Ref ConnState) (fr : Frame) (m : Method) : Async Unit := do
  if m.classId == CONNECTION && m.methodId == CONNECTION_BLOCKED then
    modSt st fun x => { x with blocked := true, sm := (tryStep x.sm .blocked).getD x.sm }
  else if m.classId == CONNECTION && m.methodId == CONNECTION_UNBLOCKED then
    modSt st fun x => { x with blocked := false, sm := (tryStep x.sm .unblocked).getD x.sm }
  else if m.classId == CONNECTION && m.methodId == CONNECTION_CLOSE then
    ioRun (failWaiters st s!"broker closed: {argStr m.args "reply_text"}")
  else if m.classId == CHANNEL && m.methodId == CHANNEL_CLOSE then
    ioRun (failWaiters st s!"channel.close {argInt m.args "reply_code"} {argStr m.args "reply_text"}")
  else if m.classId == BASIC && m.methodId == BASIC_DELIVER then
    let (props, body) ← assembleContentAio st fr.channel
    let msg : IncomingMessage := {
      deliveryTag := (argInt m.args "delivery_tag").toNat
      exchange := argStr m.args "exchange"
      routingKey := argStr m.args "routing_key"
      body, properties := props
      redelivered := argBool m.args "redelivered"
      consumerTag := argStr m.args "consumer_tag"
    }
    ioRun (offerDeliver st msg)
  else if m.classId == BASIC && m.methodId == BASIC_RETURN then
    let _ ← assembleContentAio st fr.channel
    ioRun (failWaiters st s!"basic.return {argInt m.args "reply_code"} {argStr m.args "reply_text"}")
  else if m.classId == BASIC && m.methodId == BASIC_ACK then
    let tag := (argInt m.args "delivery_tag").toNat
    let multiple := argBool m.args "multiple"
    let hit ← ioRun (resolveMethod1 st fr.channel m)
    if !hit then
      ioRun (resolveConfirm st tag multiple)
  else if m.classId == BASIC && m.methodId == BASIC_NACK then
    let tag := (argInt m.args "delivery_tag").toNat
    ioRun (failWaiters st s!"publish nack delivery_tag={tag}")
  else
    let hit ← ioRun (resolveMethod1 st fr.channel m)
    if !hit then
      pure ()

partial def pumpLoop (st : IO.Ref ConnState) : Async Unit := do
  let s ← getSt st
  if s.closed then return
  try
    let fr ← readFrameAio st
    if fr.kind == .heartbeat then
      let now ← ioRun IO.monoMsNow
      modSt st fun x => { x with lastPeerMs := now }
    else if fr.kind == .method then
      match decodeMethod fr.payload with
      | none => ioRun (failWaiters st "decodeMethod failed")
      | some m => dispatchMethod st fr m
    else
      pure ()
    pumpLoop st
  catch e =>
    ioRun (failWaiters st (toString e))

partial def heartbeatLoop (st : IO.Ref ConnState) : Async Unit := do
  let s ← getSt st
  if s.closed || s.heartbeat == 0 then return
  sleep (Std.Time.Millisecond.Offset.ofNat (s.heartbeat * 500))
  let s ← getSt st
  if s.closed then return
  let now ← ioRun IO.monoMsNow
  if now - s.lastPeerMs ≥ s.heartbeat * 2000 then
    ioRun (failWaiters st "heartbeat lost")
    return
  try
    let hb : Frame := { kind := .heartbeat, channel := 0, payload := ByteArray.empty }
    sendFrameAsync st hb
  catch _ =>
    pure ()
  heartbeatLoop st

def startPumpAsync (st : IO.Ref ConnState) : Async Unit := do
  let now ← ioRun IO.monoMsNow
  modSt st fun x => { x with pumped := true, lastPeerMs := now }
  -- Stay on the default async scheduler. `dedicated` is an OS thread; the
  -- same `SSL*` / UV handle must not be entered from two threads.
  background (pumpLoop st)
  background (heartbeatLoop st)

def expectMethodWaitAsync (st : IO.Ref ConnState) (ch classId methodId : Nat) : Async Method := do
  let s ← getSt st
  if let some msg := s.lost then throw (IO.userError msg)
  let p ← IO.Promise.new
  modSt st fun x => { x with methodWaiters := x.methodWaiters ++ [{ ch, classId, methodId, promise := p }] }
  awaitExceptAsync p

partial def expectMethodStealAio (st : IO.Ref ConnState) (ch classId methodId : Nat) : Async Method := do
  let fr ← readFrameAio st
  if fr.kind == .heartbeat then
    expectMethodStealAio st ch classId methodId
  else if fr.kind != .method then
    throw (IO.userError "expected method frame")
  else
    match decodeMethod fr.payload with
    | none => throw (IO.userError "decodeMethod failed")
    | some m =>
      if m.classId == CONNECTION && m.methodId == CONNECTION_BLOCKED then
        modSt st fun s => { s with blocked := true, sm := (tryStep s.sm .blocked).getD s.sm }
        expectMethodStealAio st ch classId methodId
      else if m.classId == CONNECTION && m.methodId == CONNECTION_UNBLOCKED then
        modSt st fun s => { s with blocked := false, sm := (tryStep s.sm .unblocked).getD s.sm }
        expectMethodStealAio st ch classId methodId
      else if m.classId == CONNECTION && m.methodId == CONNECTION_CLOSE then
        sendMethodAsync st 0 { classId := CONNECTION, methodId := CONNECTION_CLOSE_OK }
        throw (IO.userError s!"broker closed: {argStr m.args "reply_text"}")
      else if m.classId == CHANNEL && m.methodId == CHANNEL_CLOSE then
        throw (IO.userError s!"channel.close {argInt m.args "reply_code"} {argStr m.args "reply_text"}")
      else if m.classId == BASIC && m.methodId == BASIC_DELIVER then
        let (props, body) ← assembleContentAio st fr.channel
        ioRun (offerDeliver st {
          deliveryTag := (argInt m.args "delivery_tag").toNat
          exchange := argStr m.args "exchange"
          routingKey := argStr m.args "routing_key"
          body, properties := props
          redelivered := argBool m.args "redelivered"
          consumerTag := argStr m.args "consumer_tag"
        })
        expectMethodStealAio st ch classId methodId
      else if fr.channel == ch && m.classId == classId && m.methodId == methodId then
        return m
      else
        throw (IO.userError s!"unexpected method {m.classId}.{m.methodId} ch={fr.channel}")

def expectMethod (st : IO.Ref ConnState) (ch classId methodId : Nat) : Async Method :=
  expectMethodWaitAsync st ch classId methodId

/-- Prefer EXTERNAL when offered and a client cert is configured; else PLAIN. -/
def selectSasl (cfg : ConnectionConfig) (mechanisms : String) : IO (String × ByteArray) := do
  let offered := mechanisms.splitOn " "
  if offered.contains "EXTERNAL" && cfg.hasClientCert then
    return ("EXTERNAL", ByteArray.empty)
  if !offered.contains "PLAIN" then
    throwIo s!"no supported SASL mechanism in {mechanisms}"
  let response :=
    (ByteArray.empty.push 0) ++ cfg.username.toUTF8 ++
    (ByteArray.empty.push 0) ++ cfg.password.toUTF8
  return ("PLAIN", response)

/-- Shared handshake after a byte pipe exists. `useTls` steps the proven TLS SM. -/
def connectWithAsync (cfg : ConnectionConfig) (aio : AsyncByteTransport)
    (useTls : Bool := false) (fd : UInt32 := 0) : Async AmqpConnection := do
  if cfg.heartbeat = 0 ∨ cfg.heartbeat > 60 then
    throw (IO.userError s!"heartbeat must be 1..60, got {cfg.heartbeat}")
  let mut sm : NuropbRmq.Protocol.State := {}
  sm ← ioRun (stepOrThrow sm (.tcpConnected useTls))
  if useTls then
    sm ← ioRun (stepOrThrow sm .tlsVerified)
  sm ← ioRun (stepOrThrow sm .amqpHeader)
  aio.send protocolHeader
  let now ← ioRun IO.monoMsNow
  let st ← ioRun (IO.mkRef {
    fd, io := default, aio, sm, frameMax := cfg.frameMax, heartbeat := cfg.heartbeat
    buffer := ByteArray.empty, blocked := false
    lastPeerMs := now
    confirmEnabled := false, nextConfirm := 1, closed := false, inbox := []
  })
  let start ← expectMethodStealAio st 0 CONNECTION CONNECTION_START
  sm ← ioRun (stepOrThrow (← getSt st).sm .connStart)
  let (mechanism, response) ← ioRun (selectSasl cfg (argStr start.args "mechanisms"))
  if !legalSend .startOk sm.conn then throw (IO.userError "illegal start-ok")
  sendMethodAsync st 0 {
    classId := CONNECTION, methodId := CONNECTION_START_OK
    args := [
      ("client_properties", .table [("product", .longstr "nuropb-rmq"), ("version", .longstr "lean-0.1")]),
      ("mechanism", .longstr mechanism),
      ("response", .bytes response),
      ("locale", .longstr "en_US"),
    ]
  }
  sm ← ioRun (stepOrThrow sm .startOk)
  let tune ← expectMethodStealAio st 0 CONNECTION CONNECTION_TUNE
  sm ← ioRun (stepOrThrow sm .tune)
  let frameMax :=
    let fm := (argInt tune.args "frame_max").toNat
    if fm == 0 then cfg.frameMax else min fm cfg.frameMax
  let hb := min (min (argInt tune.args "heartbeat").toNat cfg.heartbeat) 60
  let hb := if hb == 0 then cfg.heartbeat else hb
  if !legalSend .tuneOk sm.conn then throw (IO.userError "illegal tune-ok")
  sendMethodAsync st 0 {
    classId := CONNECTION, methodId := CONNECTION_TUNE_OK
    args := [("channel_max", .int 2047), ("frame_max", .int frameMax), ("heartbeat", .int hb)]
  }
  sm ← ioRun (stepOrThrow sm (.tuneOk hb))
  sendMethodAsync st 0 {
    classId := CONNECTION, methodId := CONNECTION_OPEN
    args := [("virtual_host", .longstr cfg.virtualHost)]
  }
  sm ← ioRun (stepOrThrow sm .open)
  let _ ← expectMethodStealAio st 0 CONNECTION CONNECTION_OPEN_OK
  sm ← ioRun (stepOrThrow sm .openOk)
  modSt st fun s => { s with sm, frameMax, heartbeat := hb }
  startPumpAsync st
  return { config := cfg, st }

def connectAsync (cfg : ConnectionConfig := {}) : Async AmqpConnection := do
  if cfg.tls then
    throw (IO.userError "TLS requires NuropbRMQTls.connectAsync (not default lake target)")
  let sock ← connectTcpAsync cfg.host cfg.port
  connectWithAsync cfg (tcpTransportAsync sock)

/-- Alias for `connectAsync`. -/
def connect (cfg : ConnectionConfig := {}) : Async AmqpConnection :=
  connectAsync cfg

/-- Dialer value (no default cfg) for `Session.startAsync` / mesh / events. -/
def defaultDial (cfg : ConnectionConfig) : Async AmqpConnection :=
  connectAsync cfg

def close (c : AmqpConnection) : Async Unit := do
  let s ← getSt c.st
  if !s.closed && !s.sm.conn.isTerminal then
    try
      let sm ← ioRun (stepOrThrow s.sm .beginClose)
      modSt c.st fun x => { x with sm }
      let closeArgs : Table := [("reply_code", .int 200), ("reply_text", .longstr "")]
      sendMethodAsync c.st 0 { classId := CONNECTION, methodId := 50, args := closeArgs }
      let _ ← expectMethodWaitAsync c.st 0 CONNECTION 51
      let cur ← getSt c.st
      let sm' := (tryStep cur.sm .closeOk).getD cur.sm
      modSt c.st fun x => { x with sm := sm' }
    catch _ =>
      pure ()
  -- Stop the pump and waiters before `aio.close` frees TLS (`SSL_free`).
  -- Idempotent: pump errors already call `failWaiters`.
  if !(← getSt c.st).closed then
    ioRun (failWaiters c.st ((← getSt c.st).lost.getD "connection closed"))
  try (← getSt c.st).aio.close catch _ => pure ()

def openChannel (c : AmqpConnection) (channelId : Nat := 1) : Async Nat := do
  let s ← getSt c.st
  let sm ← ioRun (stepOrThrow s.sm .chanOpen)
  modSt c.st fun x => { x with sm }
  sendMethodAsync c.st channelId { classId := CHANNEL, methodId := CHANNEL_OPEN }
  let _ ← expectMethodWaitAsync c.st channelId CHANNEL CHANNEL_OPEN_OK
  let s ← getSt c.st
  let sm ← ioRun (stepOrThrow s.sm .chanOpenOk)
  modSt c.st fun x => { x with sm }
  return channelId

def confirmSelectAsync (c : AmqpConnection) (channelId : Nat) : Async Unit := do
  let s ← getSt c.st
  if s.confirmEnabled then return
  sendMethodAsync c.st channelId { classId := CONFIRM, methodId := CONFIRM_SELECT }
  let _ ← expectMethodWaitAsync c.st channelId CONFIRM CONFIRM_SELECT_OK
  modSt c.st fun x => { x with confirmEnabled := true }

def confirmSelect (c : AmqpConnection) (channelId : Nat) : Async Unit :=
  confirmSelectAsync c channelId

def publishFrames (channelId : Nat) (body : ByteArray) (exchange routingKey : String)
    (props : BasicProperties) (mandatory : Bool) (frameMax : Nat) : IO (List Frame) := do
  match encodeMethod {
    classId := BASIC, methodId := BASIC_PUBLISH
    args := [
      ("exchange", .longstr exchange), ("routing_key", .longstr routingKey),
      ("mandatory", .bool mandatory),
    ]
  } with
  | none => throwIo "encodeMethod failed basic.publish"
  | some pub =>
    match encodeContentHeader BASIC body.size props with
    | none => throwIo "encodeContentHeader failed"
    | some header =>
      let payloadMax := (maxFramePayload frameMax).getD 131064
      let mut frames : List Frame := [
        { kind := .method, channel := channelId, payload := pub },
        { kind := .header, channel := channelId, payload := header },
      ]
      if body.size == 0 then
        frames := frames ++ [{ kind := .body, channel := channelId, payload := ByteArray.empty }]
      else
        let mut off := 0
        while off < body.size do
          let n := min payloadMax (body.size - off)
          frames := frames ++ [{
            kind := .body, channel := channelId, payload := body.extract off (off + n)
          }]
          off := off + n
      return frames

/-- Method+header+one body frame in one `ByteArray` (small payloads). Larger bodies
    fall back to `publishFrames` + `encodeBurst`. -/
def encodePublish (channelId : Nat) (body : ByteArray) (exchange routingKey : String)
    (props : BasicProperties) (mandatory : Bool) (frameMax : Nat) : IO ByteArray := do
  match encodeMethod {
    classId := BASIC, methodId := BASIC_PUBLISH
    args := [
      ("exchange", .longstr exchange), ("routing_key", .longstr routingKey),
      ("mandatory", .bool mandatory),
    ]
  } with
  | none => throwIo "encodeMethod failed basic.publish"
  | some pub =>
    match encodeContentHeader BASIC body.size props with
    | none => throwIo "encodeContentHeader failed"
    | some header =>
      let payloadMax := (maxFramePayload frameMax).getD 131064
      if body.size > payloadMax then
        let frames ← publishFrames channelId body exchange routingKey props mandatory frameMax
        match encodeBurst frames frameMax with
        | none => throwIo "encodeBurst failed (frame_max)"
        | some raw => return raw
      else
        match encodeBurst [
          { kind := .method, channel := channelId, payload := pub },
          { kind := .header, channel := channelId, payload := header },
          { kind := .body, channel := channelId, payload := body },
        ] frameMax with
        | none => throwIo "encodeBurst failed (frame_max)"
        | some raw => return raw

def ackMethod (deliveryTag : Nat) : Method :=
  { classId := BASIC, methodId := BASIC_ACK, args := [("delivery_tag", .int deliveryTag)] }

def encodeAckFrame (channelId deliveryTag : Nat) (frameMax : Nat) : IO ByteArray := do
  match encodeMethod (ackMethod deliveryTag) with
  | none => throwIo "encodeMethod failed basic.ack"
  | some payload =>
    match encodeFrame { kind := .method, channel := channelId, payload } frameMax with
    | none => throwIo "encodeFrame failed basic.ack"
    | some raw => return raw

def exchangeDeclare (c : AmqpConnection) (channelId : Nat) (exchange type_ : String)
    (durable autoDelete : Bool := false) : Async Unit := do
  sendMethodAsync c.st channelId {
    classId := EXCHANGE, methodId := EXCHANGE_DECLARE
    args := [
      ("exchange", .longstr exchange), ("type", .longstr type_),
      ("durable", .bool durable), ("auto_delete", .bool autoDelete),
    ]
  }
  let _ ← expectMethodWaitAsync c.st channelId EXCHANGE EXCHANGE_DECLARE_OK

def queueDeclare (c : AmqpConnection) (channelId : Nat) (queue : String)
    (durable exclusive autoDelete : Bool := false) (arguments : Table := []) : Async String := do
  sendMethodAsync c.st channelId {
    classId := QUEUE, methodId := QUEUE_DECLARE
    args := [
      ("queue", .longstr queue), ("durable", .bool durable),
      ("exclusive", .bool exclusive), ("auto_delete", .bool autoDelete),
      ("arguments", .table arguments),
    ]
  }
  let ok ← expectMethodWaitAsync c.st channelId QUEUE QUEUE_DECLARE_OK
  return argStr ok.args "queue"

def queueBind (c : AmqpConnection) (channelId : Nat) (queue exchange routingKey : String) : Async Unit := do
  sendMethodAsync c.st channelId {
    classId := QUEUE, methodId := QUEUE_BIND
    args := [
      ("queue", .longstr queue), ("exchange", .longstr exchange),
      ("routing_key", .longstr routingKey),
    ]
  }
  let _ ← expectMethodWaitAsync c.st channelId QUEUE QUEUE_BIND_OK

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
    (deliveryLimit : Option Nat := none) : Async String := do
  if queueType == "quorum" && (exclusive || autoDelete) then
    throw (IO.userError "quorum queues cannot be exclusive or auto-delete")
  if let some x := dlx then
    exchangeDeclare c channelId x "topic" (durable := true)
  queueDeclare c channelId queue durable exclusive autoDelete
    (profileArgs durableAtLeastOnce queue dlx ttlMs queueType dlrk deliveryLimit)

/-- Publish and register a confirm waiter without awaiting it. -/
def basicPublishKickAsync (c : AmqpConnection) (channelId : Nat) (body : ByteArray)
    (exchange routingKey : String := "") (props : BasicProperties := {})
    (mandatory : Bool := false) (wantConfirm : Bool := false) :
    Async (Option (IO.Promise (Except IO.Error Unit))) := do
  let s ← getSt c.st
  if s.blocked || !publishAllowed s.sm then
    throw (IO.userError "connection.blocked — publish refused")
  if wantConfirm && !s.confirmEnabled then
    confirmSelectAsync c channelId
  let mut confirmP : Option (IO.Promise (Except IO.Error Unit)) := none
  if (wantConfirm || (← getSt c.st).confirmEnabled) && (← getSt c.st).pumped then
    let p ← IO.Promise.new
    confirmP := some p
    modSt c.st fun x => {
      x with
      nextConfirm := x.nextConfirm + 1
      confirmWaiters := x.confirmWaiters.insert x.nextConfirm p
    }
  let raw ← ioRun (encodePublish channelId body exchange routingKey props mandatory s.frameMax)
  if s.pumped then
    sendRawAsync c.st raw
  else
    s.aio.send raw
  if confirmP.isNone && (wantConfirm || (← getSt c.st).confirmEnabled) then
    let _ ← expectMethodWaitAsync c.st channelId BASIC BASIC_ACK
  return confirmP

def basicPublishAsync (c : AmqpConnection) (channelId : Nat) (body : ByteArray)
    (exchange routingKey : String := "") (props : BasicProperties := {})
    (mandatory : Bool := false) (wantConfirm : Bool := false) : Async Unit := do
  match ← basicPublishKickAsync c channelId body exchange routingKey props mandatory wantConfirm with
  | some p => awaitExceptAsync p
  | none => pure ()

def basicPublish (c : AmqpConnection) (channelId : Nat) (body : ByteArray)
    (exchange routingKey : String := "") (props : BasicProperties := {})
    (mandatory : Bool := false) (wantConfirm : Bool := false) : Async Unit :=
  basicPublishAsync c channelId body exchange routingKey props mandatory wantConfirm

/-- Reply publish + request `basic.ack` in one write lock / one `aio.send`. -/
def publishAndAckAsync (c : AmqpConnection) (channelId : Nat) (body : ByteArray)
    (exchange routingKey : String) (props : BasicProperties) (deliveryTag : Nat) : Async Unit := do
  let s ← getSt c.st
  if s.blocked || !publishAllowed s.sm then
    throw (IO.userError "connection.blocked — publish refused")
  let pub ← ioRun (encodePublish channelId body exchange routingKey props false s.frameMax)
  let ack ← ioRun (encodeAckFrame channelId deliveryTag s.frameMax)
  if s.pumped then
    sendRawAsync c.st (pub ++ ack)
  else
    s.aio.send (pub ++ ack)

def basicConsume (c : AmqpConnection) (channelId : Nat) (queue : String) : Async String := do
  sendMethodAsync c.st channelId {
    classId := BASIC, methodId := BASIC_CONSUME
    args := [("queue", .longstr queue)]
  }
  let ok ← expectMethodWaitAsync c.st channelId BASIC BASIC_CONSUME_OK
  return argStr ok.args "consumer_tag"

def basicAckAsync (c : AmqpConnection) (channelId deliveryTag : Nat) : Async Unit :=
  sendMethodAsync c.st channelId {
    classId := BASIC, methodId := BASIC_ACK
    args := [("delivery_tag", .int deliveryTag)]
  }

def basicAck (c : AmqpConnection) (channelId deliveryTag : Nat) : Async Unit :=
  basicAckAsync c channelId deliveryTag

def basicNack (c : AmqpConnection) (channelId deliveryTag : Nat) (requeue : Bool := false) : Async Unit :=
  sendMethodAsync c.st channelId {
    classId := BASIC, methodId := BASIC_NACK
    args := [("delivery_tag", .int deliveryTag), ("requeue", .bool requeue)]
  }

/-- Pop inbox or register a deliver waiter in one `modifyGet` so a racing
    `offerDeliver` cannot land in the inbox while we wait on an empty table. -/
def takeDeliver (st : IO.Ref ConnState) (p : IO.Promise (Except IO.Error IncomingMessage)) :
    IO (Except String (Option IncomingMessage)) :=
  st.modifyGet fun s =>
    if let some msg := s.lost then
      (.error msg, s)
    else
      match s.inbox with
      | msg :: rest => (.ok (some msg), { s with inbox := rest })
      | [] => (.ok none, { s with deliverWaiters := s.deliverWaiters ++ [p] })

def receiveWaitAsync (st : IO.Ref ConnState) : Async IncomingMessage := do
  let p ← IO.Promise.new
  match ← ioRun (takeDeliver st p) with
  | .error msg => throw (IO.userError msg)
  | .ok (some msg) => return msg
  | .ok none => awaitExceptAsync p

def receiveAsync (c : AmqpConnection) (_timeoutMs : Nat := 30000) : Async IncomingMessage :=
  receiveWaitAsync c.st

def receive (c : AmqpConnection) (timeoutMs : Nat := 30000) : Async IncomingMessage :=
  receiveAsync c timeoutMs

def updateSecret (c : AmqpConnection) (newSecret reason : String) : Async Unit := do
  let s ← getSt c.st
  if !legalSend .updateSecret s.sm.conn then throw (IO.userError "illegal update-secret")
  sendMethodAsync c.st 0 {
    classId := CONNECTION, methodId := CONNECTION_UPDATE_SECRET
    args := [("new_secret", .longstr newSecret), ("reason", .longstr reason)]
  }
  let _ ← expectMethodWaitAsync c.st 0 CONNECTION CONNECTION_UPDATE_SECRET_OK
  let sm ← ioRun (stepOrThrow s.sm .updateSecret)
  modSt c.st fun x => { x with sm }

def timeoutReplyWaiter (st : IO.Ref ConnState) (rid : String)
    (p : IO.Promise (Except IO.Error IncomingMessage)) : IO Unit := do
  let still ← st.modifyGet fun s =>
    match s.replyWaiters.get? rid with
    | some _ => (true, { s with replyWaiters := s.replyWaiters.erase rid })
    | none => (false, s)
  if still then
    p.resolve (.error (IO.userError "REQUEST_TIMEOUT"))

def takeReply (st : IO.Ref ConnState) (rid : String)
    (p : IO.Promise (Except IO.Error IncomingMessage)) :
    IO (Except String (Option IncomingMessage)) :=
  st.modifyGet fun s =>
    if let some msg := s.lost then
      (.error msg, s)
    else
      match s.inbox.find? (fun m => m.properties.correlationId == some rid) with
      | some msg =>
        (.ok (some msg),
          { s with inbox := s.inbox.filter (fun m => m.properties.correlationId != some rid) })
      | none =>
        (.ok none, { s with replyWaiters := s.replyWaiters.insert rid p })

def waitReplyWaiterAsync (st : IO.Ref ConnState) (rid : String) (timeoutMs : Nat := 60000) :
    Async IncomingMessage := do
  let p ← IO.Promise.new
  match ← ioRun (takeReply st rid p) with
  | .error msg => throw (IO.userError msg)
  | .ok (some msg) => return msg
  | .ok none =>
    if timeoutMs == 0 then
      awaitExceptAsync p
    else
      Async.race (awaitExceptAsync p) (do
        sleep (Std.Time.Millisecond.Offset.ofNat timeoutMs)
        ioRun (timeoutReplyWaiter st rid p)
        throw (IO.userError "REQUEST_TIMEOUT"))

end NuropbRMQ
