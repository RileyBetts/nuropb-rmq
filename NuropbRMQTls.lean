/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQ.Config
import NuropbRMQ.Socket
import NuropbRMQ.Transport
import NuropbRMQ.Connection

/-!
Optional AMQPS (tls-verify-full). Build: `lake build NuropbRMQTls`
(requires OpenSSL). Not a default target.
-/

namespace NuropbRMQ.Tls

@[extern "nuropb_tls_connect"]
opaque connectSsl (fd : UInt32) (hostname caPem certPem keyPem : @& String) : IO UInt64

@[extern "nuropb_tls_connect_pkcs12"]
opaque connectSslPkcs12 (fd : UInt32) (hostname caPem p12Path password : @& String) : IO UInt64

@[extern "nuropb_tls_send"]
opaque sendSsl (handle : UInt64) (buf : @& ByteArray) : IO Unit

@[extern "nuropb_tls_recv"]
opaque recvSsl (handle : UInt64) (max : UInt32) : IO ByteArray

@[extern "nuropb_tls_pending"]
opaque pending (handle : UInt64) : IO Bool

@[extern "nuropb_tls_close"]
opaque closeSsl (handle : UInt64) : IO Unit

def readFileOrEmpty (path : Option String) : IO String := do
  match path with
  | none => return ""
  | some p => IO.FS.readFile p

/-- TCP then TLS handshake with peer hostname verification. -/
def wrapFd (fd : UInt32) (hostname : String) (cfg : ConnectionConfig) : IO UInt64 := do
  if cfg.pkcs12File.isSome && (cfg.certFile.isSome || cfg.keyFile.isSome) then
    throw (IO.userError "pkcs12: conflicts with PEM cert")
  let ca ← readFileOrEmpty cfg.caFile
  match cfg.pkcs12File with
  | some p =>
    -- Bind before the `@& String` extern so GC cannot collect the password.
    let pass := cfg.pkcs12Password.getD ""
    connectSslPkcs12 fd hostname ca p pass
  | none =>
    let cert ← readFileOrEmpty cfg.certFile
    let key ← readFileOrEmpty cfg.keyFile
    connectSsl fd hostname ca cert key

def tlsTransport (fd : UInt32) (handle : UInt64) : Transport where
  send := fun buf => sendSsl handle buf
  recv := fun n => recvSsl handle n
  poll := fun ms => do
    if (← pending handle) then return true
    Socket.poll fd ms
  close := do
    try closeSsl handle catch _ => pure ()
    Socket.close fd

/-- AMQPS connect (tls-verify-full). Does not change the POSIX `NuropbRMQ.connect`. -/
def connect (cfg : ConnectionConfig := {}) : IO AmqpConnection := do
  let fd ← Socket.connect cfg.host cfg.port
  let hn := cfg.serverHostname.getD cfg.host
  let h ← wrapFd fd hn cfg
  connectWith { cfg with tls := true } (tlsTransport fd h) true fd

end NuropbRMQ.Tls

namespace NuropbRMQTls
/-- Alias matching the Lake target / docs. -/
def connect (cfg : NuropbRMQ.ConnectionConfig := {}) : IO NuropbRMQ.AmqpConnection :=
  NuropbRMQ.Tls.connect cfg
end NuropbRMQTls
