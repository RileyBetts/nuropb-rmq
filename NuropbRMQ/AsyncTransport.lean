/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async.TCP
import Std.Net.Addr
import NuropbRMQ.Transport

/-!
Byte pipes matching lean-grpc `H2.Transport` (v1.3.0): native `Std.Async.TCP`
with no `.block` on the library path. `Transport.ofAsync` exists only for the
loopback smoke. AMQPS is a memory-BIO pipe on `NuropbRMQTls`, not off-loop
`SSL_*`.
-/

open Std.Async
open Std.Net

namespace NuropbRMQ

/-- Async byte pipe (PLAIN TCP). Prefer this over `Transport` when composing
    under `Std.Async` so send/recv do not call `.block`. -/
structure AsyncByteTransport where
  send : ByteArray → Async Unit
  recv? : Nat → Async (Option ByteArray)
  close : Async Unit := pure ()

instance : Inhabited AsyncByteTransport where
  default := {
    send := fun _ => throw (IO.userError "no async transport")
    recv? := fun _ => throw (IO.userError "no async transport")
    close := pure ()
  }

/-- Wrap a connected `Std.Async` TCP client without `.block`. -/
def tcpTransportAsync (sock : TCP.Socket.Client) : AsyncByteTransport where
  send := fun b => sock.send b
  recv? := fun n => sock.recv? n.toUInt64
  close := pure ()

/-- Sync adapter for the loopback smoke. Not used by AMQP handshake. -/
def Transport.ofAsync (t : AsyncByteTransport) : Transport where
  send := fun b => (t.send b).block
  recv := fun n => do
    match ← (t.recv? n.toNat).block with
    | some b => return b
    | none => throw (IO.userError "connection closed")
  poll := fun _ => pure true
  close := t.close.block

/-- IPv4 (or `localhost`) for `Std.Async.TCP`. Not a second TCP stack. -/
def resolveAddr (host : String) (port : UInt16) : IO SocketAddress := do
  let h := if host == "localhost" || host == "localhost." then "127.0.0.1" else host
  match IPv4Addr.ofString h with
  | some a => return .v4 { addr := a, port }
  | none =>
    throw (IO.userError s!"Std.Async.TCP requires an IPv4 address (got {host})")

/-- Dial without `.block`. -/
def connectTcpAsync (host : String) (port : UInt16) : Async TCP.Socket.Client := do
  let sock ← TCP.Socket.Client.mk
  let addr ← liftM (resolveAddr host port)
  sock.connect addr
  -- `noDelay` sets TCP_NODELAY (disables Nagle) so small AMQP frames flush.
  liftM (sock.noDelay : IO Unit)
  return sock

end NuropbRMQ
