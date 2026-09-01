/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
URL-safe Base64 without required padding (JWT compact serialization).
-/

namespace NuropbRmq.Crypto

def b64Alphabet : String :=
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"

def b64Val (c : Char) : Option Nat :=
  if c = '-' then some 62
  else if c = '_' then some 63
  else if 'A' ≤ c ∧ c ≤ 'Z' then some (c.toNat - 'A'.toNat)
  else if 'a' ≤ c ∧ c ≤ 'z' then some (c.toNat - 'a'.toNat + 26)
  else if '0' ≤ c ∧ c ≤ '9' then some (c.toNat - '0'.toNat + 52)
  else none

partial def addPad (s : String) : String :=
  if s.length % 4 = 0 then s
  else addPad (s.push '=')

def decodeQuad (a b c d : Nat) : Array UInt8 :=
  let n := (a <<< 18) ||| (b <<< 12) ||| (c <<< 6) ||| d
  #[ UInt8.ofNat ((n >>> 16) &&& 255)
   , UInt8.ofNat ((n >>> 8) &&& 255)
   , UInt8.ofNat (n &&& 255) ]

def decodeBase64Url (s : String) : Option ByteArray :=
  let padded := addPad (s.replace "=" "")
  if padded.length % 4 ≠ 0 then none
  else
    Id.run do
      let mut out : ByteArray := ByteArray.empty
      let mut i := 0
      while i < padded.length do
        let ca := padded.get! ⟨i⟩
        let cb := padded.get! ⟨i+1⟩
        let cc := padded.get! ⟨i+2⟩
        let cd := padded.get! ⟨i+3⟩
        let va := if ca = '=' then some 0 else b64Val ca
        let vb := if cb = '=' then some 0 else b64Val cb
        let vc := if cc = '=' then some 0 else b64Val cc
        let vd := if cd = '=' then some 0 else b64Val cd
        match va, vb, vc, vd with
        | some a, some b, some c, some d =>
            let q := decodeQuad a b c d
            out := out.push q[0]!
            if cc ≠ '=' then out := out.push q[1]!
            if cd ≠ '=' then out := out.push q[2]!
            i := i + 4
        | _, _, _, _ => return none
      pure (some out)

end NuropbRmq.Crypto
