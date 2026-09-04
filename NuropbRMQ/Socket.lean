/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

namespace NuropbRMQ.Socket

@[extern "nuropb_tcp_connect"]
opaque connect (host : @& String) (port : UInt16) : IO UInt32

@[extern "nuropb_tcp_send"]
opaque send (fd : UInt32) (buf : @& ByteArray) : IO Unit

@[extern "nuropb_tcp_recv"]
opaque recv (fd : UInt32) (max : UInt32) : IO ByteArray

@[extern "nuropb_tcp_poll"]
opaque poll (fd : UInt32) (timeoutMs : UInt32) : IO Bool

@[extern "nuropb_tcp_close"]
opaque close (fd : UInt32) : IO Unit

@[extern "nuropb_random_bytes"]
opaque randomBytes (n : UInt32) : IO ByteArray

def hexNibble (n : Nat) : Char :=
  if n < 10 then Char.ofNat (48 + n) else Char.ofNat (87 + n)

def hexId : IO String := do
  let raw ← randomBytes 16
  let mut s := ""
  for i in [0:raw.size] do
    let b := raw.get! i |>.toNat
    s := s.push (hexNibble (b >>> 4)) |>.push (hexNibble (b &&& 15))
  return s

end NuropbRMQ.Socket
