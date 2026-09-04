/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQ.Socket

/-!
Byte pipe for AMQP. PLAIN uses POSIX sockets. AMQPS supplies a TLS pipe from
`NuropbRMQTls` without linking OpenSSL into the default client.
-/

namespace NuropbRMQ

structure Transport where
  send : ByteArray → IO Unit
  recv : UInt32 → IO ByteArray
  poll : UInt32 → IO Bool
  close : IO Unit

def posixTransport (fd : UInt32) : Transport where
  send := fun buf => Socket.send fd buf
  recv := fun n => Socket.recv fd n
  poll := fun ms => Socket.poll fd ms
  close := Socket.close fd

instance : Inhabited Transport where
  default := {
    send := fun _ => throw (IO.userError "no transport")
    recv := fun _ => throw (IO.userError "no transport")
    poll := fun _ => pure false
    close := pure ()
  }

end NuropbRMQ
