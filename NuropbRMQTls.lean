/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQ.Socket

/-!
Optional AMQPS (tls-verify-full). Build: `lake build NuropbRMQTls`
(requires OpenSSL). Not a default target.
-/

namespace NuropbRMQ.Tls

@[extern "nuropb_tls_connect"]
opaque connect (fd : UInt32) (hostname caPem certPem keyPem : @& String) : IO UInt64

@[extern "nuropb_tls_send"]
opaque send (handle : UInt64) (buf : @& ByteArray) : IO Unit

@[extern "nuropb_tls_recv"]
opaque recv (handle : UInt64) (max : UInt32) : IO ByteArray

@[extern "nuropb_tls_close"]
opaque close (handle : UInt64) : IO Unit

def readFileOrEmpty (path : Option String) : IO String := do
  match path with
  | none => return ""
  | some p => IO.FS.readFile p

/-- TCP then TLS handshake with peer hostname verification. -/
def wrapFd (fd : UInt32) (hostname : String) (caFile certFile keyFile : Option String) : IO UInt64 := do
  let ca ← readFileOrEmpty caFile
  let cert ← readFileOrEmpty certFile
  let key ← readFileOrEmpty keyFile
  connect fd hostname ca cert key

end NuropbRMQ.Tls
