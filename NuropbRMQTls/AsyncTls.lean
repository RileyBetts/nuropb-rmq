/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Std.Async.TCP
import NuropbRMQ.Config
import NuropbRMQ.AsyncTransport
import NuropbRMQ.Connection

/-!
UV-loop AMQPS byte pipe. OpenSSL sees memory BIOs only; `Std.Async.TCP` owns
the socket. An async mutex serializes `SSL_*` so the pump recv and write
flusher never enter the session together.
-/

open Std.Async

namespace NuropbRMQ.Tls

@[extern "nuropb_tls_new"]
opaque newSsl (hostname caPem certPem keyPem : @& String) : IO UInt64

@[extern "nuropb_tls_new_pkcs12"]
opaque newSslPkcs12 (hostname caPem p12Path password : @& String) : IO UInt64

@[extern "nuropb_tls_handshake_step"]
opaque handshakeStep (handle : UInt64) : IO Nat

@[extern "nuropb_tls_feed"]
opaque feedSsl (handle : UInt64) (buf : @& ByteArray) : IO Unit

@[extern "nuropb_tls_drain"]
opaque drainSsl (handle : UInt64) : IO ByteArray

@[extern "nuropb_tls_write"]
opaque writeSsl (handle : UInt64) (buf : @& ByteArray) : IO UInt64

@[extern "nuropb_tls_read"]
opaque readSsl (handle : UInt64) (max : UInt32) : IO ByteArray

@[extern "nuropb_tls_pending"]
opaque pendingSsl (handle : UInt64) : IO Bool

@[extern "nuropb_tls_last_want"]
opaque lastWant (handle : UInt64) : IO Nat

@[extern "nuropb_tls_shutdown_step"]
opaque shutdownStep (handle : UInt64) : IO Nat

@[extern "nuropb_tls_close"]
opaque closeSsl (handle : UInt64) : IO Unit

def tlsWantDone : Nat := 0
def tlsWantRead : Nat := 1
def tlsWantWrite : Nat := 2

def unpackWant (packed : UInt64) : Nat × Nat :=
  let st := (packed >>> 32).toNat
  let n := (packed &&& 0xffffffff).toNat
  (st, n)

structure SslGateState where
  busy : Bool := false
  waiters : List (IO.Promise (Except IO.Error Unit)) := []

structure SslGate where
  st : IO.Ref SslGateState

def SslGate.new : IO SslGate := do
  return { st := ← IO.mkRef {} }

def SslGate.acquire (g : SslGate) : Async Unit := do
  let p ← IO.Promise.new
  let immediate ← ioRun (g.st.modifyGet fun s =>
    if !s.busy && s.waiters.isEmpty then
      (true, { s with busy := true })
    else
      (false, { s with busy := true, waiters := s.waiters ++ [p] }))
  unless immediate do
    awaitExceptAsync p

def SslGate.release (g : SslGate) : Async Unit := do
  let nxt ← ioRun (g.st.modifyGet fun s =>
    match s.waiters with
    | p :: rest => (some p, { s with waiters := rest })
    | [] => (none, { s with busy := false }))
  match nxt with
  | some p => ioRun (p.resolve (.ok ()))
  | none => pure ()

/-- Run an `IO` OpenSSL call under the session lock. Do not await TCP here. -/
def SslGate.sslIO (g : SslGate) (act : IO α) : Async α := do
  SslGate.acquire g
  try
    let r ← ioRun act
    SslGate.release g
    return r
  catch e =>
    SslGate.release g
    throw e

/-- Hold the gate across an `Async` section (e.g. one `sock.recv?`). -/
def SslGate.withAsync (g : SslGate) (act : Async α) : Async α := do
  SslGate.acquire g
  try
    let r ← act
    SslGate.release g
    return r
  catch e =>
    SslGate.release g
    throw e

/-- UV socket + memory-BIO session. `recv` serializes TCP `recv?` (libuv
    forbids parallel recv on one client). `alive` is cleared before `SSL_free`
    so a pump blocked in `recv?` cannot re-enter OpenSSL after close. -/
structure TlsPipe where
  sock : TCP.Socket.Client
  handle : UInt64
  ssl : SslGate
  recv : SslGate
  alive : IO.Ref Bool

def TlsPipe.new (sock : TCP.Socket.Client) (handle : UInt64) : IO TlsPipe := do
  return {
    sock, handle
    ssl := ← SslGate.new
    recv := ← SslGate.new
    alive := ← IO.mkRef true
  }

def sendCipher (sock : TCP.Socket.Client) (ciph : ByteArray) : Async Unit := do
  if ciph.size == 0 then return
  sock.send ciph

/-- Only TCP-recv entry after handshake. Serialized; never feeds a freed `SSL*`. -/
def feedRecv (p : TlsPipe) : Async Bool :=
  SslGate.withAsync p.recv do
    match ← p.sock.recv? (16384 : UInt64) with
    | none => return false
    | some b =>
      if b.size == 0 then return false
      SslGate.sslIO p.ssl do
        if !(← p.alive.get) then return false
        feedSsl p.handle b
        return true

partial def handshakeLoop (sock : TCP.Socket.Client) (handle : UInt64) : Async Unit := do
  let st ← ioRun (handshakeStep handle)
  let pending ← ioRun (drainSsl handle)
  if pending.size > 0 then
    sock.send pending
  if st == tlsWantDone then
    pure ()
  else if st == tlsWantRead then
    match ← sock.recv? (16384 : UInt64) with
    | none => throw (IO.userError "TLS handshake: connection closed")
    | some b =>
      if b.size == 0 then throw (IO.userError "TLS handshake: connection closed")
      ioRun (feedSsl handle b)
    handshakeLoop sock handle
  else if st == tlsWantWrite then
    handshakeLoop sock handle
  else
    throw (IO.userError "TLS handshake failed")

partial def writeAll (p : TlsPipe) (buf : ByteArray) (off : Nat) : Async Unit := do
  if off ≥ buf.size then
    let ciph ← SslGate.sslIO p.ssl do
      if !(← p.alive.get) then return ByteArray.empty
      drainSsl p.handle
    sendCipher p.sock ciph
    return
  let rest := buf.extract off buf.size
  let (packed, ciph) ← SslGate.sslIO p.ssl do
    if !(← p.alive.get) then
      throw (IO.userError "TLS session closed")
    let packed ← writeSsl p.handle rest
    let ciph ← drainSsl p.handle
    return (packed, ciph)
  let (st, n) := unpackWant packed
  sendCipher p.sock ciph
  if st == tlsWantDone then
    writeAll p buf (off + n)
  else if st == tlsWantRead then
    unless (← feedRecv p) do
      throw (IO.userError "TLS write: connection closed")
    writeAll p buf off
  else if st == tlsWantWrite then
    writeAll p buf off
  else
    throw (IO.userError "TLS write failed")

partial def readSome (p : TlsPipe) (max : Nat) : Async (Option ByteArray) := do
  let (data, st, ciph) ← SslGate.sslIO p.ssl do
    if !(← p.alive.get) then
      return (ByteArray.empty, tlsWantDone, ByteArray.empty)
    let data ← readSsl p.handle max.toUInt32
    let st ←
      if data.size > 0 then pure tlsWantDone
      else lastWant p.handle
    let ciph ← drainSsl p.handle
    return (data, st, ciph)
  sendCipher p.sock ciph
  if data.size > 0 then
    return some data
  if st == tlsWantDone then
    return none
  else if st == tlsWantRead then
    unless (← feedRecv p) do
      return none
    readSome p max
  else if st == tlsWantWrite then
    readSome p max
  else
    throw (IO.userError "TLS read failed")

def tlsTransportAsync (p : TlsPipe) : AsyncByteTransport where
  send := fun b => writeAll p b 0
  recv? := fun n => readSome p n
  close := do
    try
      let ciph ← SslGate.sslIO p.ssl do
        if !(← p.alive.get) then return ByteArray.empty
        let _ ← shutdownStep p.handle
        drainSsl p.handle
      sendCipher p.sock ciph
    catch _ =>
      pure ()
    try
      SslGate.sslIO p.ssl do
        unless (← p.alive.get) do return
        p.alive.set false
        closeSsl p.handle
    catch _ =>
      ioRun (p.alive.set false)
    try p.sock.shutdown catch _ => pure ()

def readFileOrEmpty (path : Option String) : IO String := do
  match path with
  | none => return ""
  | some p => IO.FS.readFile p

/-- Allocate an OpenSSL session (no handshake, no fd). -/
def newHandle (hostname : String) (cfg : ConnectionConfig) : IO UInt64 := do
  if cfg.pkcs12File.isSome && (cfg.certFile.isSome || cfg.keyFile.isSome) then
    throw (IO.userError "pkcs12: conflicts with PEM cert")
  let ca ← readFileOrEmpty cfg.caFile
  match cfg.pkcs12File with
  | some p =>
    let pass := cfg.pkcs12Password.getD ""
    newSslPkcs12 hostname ca p pass
  | none =>
    let cert ← readFileOrEmpty cfg.certFile
    let key ← readFileOrEmpty cfg.keyFile
    newSsl hostname ca cert key

end NuropbRMQ.Tls
