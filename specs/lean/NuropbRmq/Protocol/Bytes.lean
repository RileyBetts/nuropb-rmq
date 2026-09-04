/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Big-endian wire helpers for AMQP 0-9-1 frames and methods.
-/

namespace NuropbRmq.Protocol.Bytes

def pushU8 (buf : ByteArray) (v : UInt8) : ByteArray :=
  buf.push v

def pushU16be (buf : ByteArray) (v : Nat) : ByteArray :=
  buf.push (UInt8.ofNat ((v >>> 8) &&& 255)) |>.push (UInt8.ofNat (v &&& 255))

def pushU32be (buf : ByteArray) (v : Nat) : ByteArray :=
  buf.push (UInt8.ofNat ((v >>> 24) &&& 255))
    |>.push (UInt8.ofNat ((v >>> 16) &&& 255))
    |>.push (UInt8.ofNat ((v >>> 8) &&& 255))
    |>.push (UInt8.ofNat (v &&& 255))

def pushU64be (buf : ByteArray) (v : Nat) : ByteArray :=
  let hi := v >>> 32
  let lo := v &&& 0xffffffff
  pushU32be (pushU32be buf hi) lo

def pushI32be (buf : ByteArray) (v : Int) : ByteArray :=
  let n := (v % (2 ^ 32) + (2 ^ 32)) % (2 ^ 32)
  pushU32be buf n.toNat

def getU8 (data : ByteArray) (off : Nat) : Option (UInt8 × Nat) :=
  if off < data.size then some (data.get! off, off + 1) else none

def getU16be (data : ByteArray) (off : Nat) : Option (Nat × Nat) :=
  if off + 2 ≤ data.size then
    let hi := data.get! off |>.toNat
    let lo := data.get! (off + 1) |>.toNat
    some (hi <<< 8 ||| lo, off + 2)
  else none

def getU32be (data : ByteArray) (off : Nat) : Option (Nat × Nat) :=
  if off + 4 ≤ data.size then
    let b0 := data.get! off |>.toNat
    let b1 := data.get! (off + 1) |>.toNat
    let b2 := data.get! (off + 2) |>.toNat
    let b3 := data.get! (off + 3) |>.toNat
    some (b0 <<< 24 ||| b1 <<< 16 ||| b2 <<< 8 ||| b3, off + 4)
  else none

def getU64be (data : ByteArray) (off : Nat) : Option (Nat × Nat) :=
  match getU32be data off with
  | none => none
  | some (hi, off') =>
    match getU32be data off' with
    | none => none
    | some (lo, off'') => some (hi <<< 32 ||| lo, off'')

def getI32be (data : ByteArray) (off : Nat) : Option (Int × Nat) :=
  match getU32be data off with
  | none => none
  | some (n, off') =>
    let i := Int.ofNat n
    some (if i ≥ 0x80000000 then i - 0x100000000 else i, off')

def slice (data : ByteArray) (off len : Nat) : Option ByteArray :=
  if off + len ≤ data.size then some (data.extract off (off + len)) else none

def hexDigit (c : Char) : Option Nat :=
  let n := c.toNat
  if n ≥ 48 ∧ n ≤ 57 then some (n - 48)
  else if n ≥ 97 ∧ n ≤ 102 then some (n - 87)
  else if n ≥ 65 ∧ n ≤ 70 then some (n - 55)
  else none

partial def fromHexList (cs : List Char) (acc : ByteArray) : Option ByteArray :=
  match cs with
  | [] => some acc
  | c1 :: c2 :: rest =>
    match hexDigit c1, hexDigit c2 with
    | some a, some b => fromHexList rest (acc.push (UInt8.ofNat (a <<< 4 ||| b)))
    | _, _ => none
  | _ => none

def fromHex (s : String) : Option ByteArray :=
  if s.length % 2 ≠ 0 then none else fromHexList s.toList ByteArray.empty

def hexNibble (n : Nat) : Char :=
  if n < 10 then Char.ofNat (48 + n) else Char.ofNat (87 + n)

def toHex (data : ByteArray) : String :=
  Id.run do
    let mut s := ""
    for i in [0:data.size] do
      let b := data.get! i |>.toNat
      s := s.push (hexNibble (b >>> 4)) |>.push (hexNibble (b &&& 15))
    pure s

def utf8 (s : String) : ByteArray := s.toUTF8

def fromUtf8 (b : ByteArray) : Option String := String.fromUTF8? b

end NuropbRmq.Protocol.Bytes
