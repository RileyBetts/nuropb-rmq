/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Crypto.Sha256

namespace NuropbRmq.Crypto

def xorByte (a b : UInt8) : UInt8 := a ^^^ b

def padKey (key : ByteArray) (block : Nat) : ByteArray :=
  let k := if key.size > block then sha256 key else key
  Id.run do
    let mut out := k
    while out.size < block do
      out := out.push 0
    pure out

def xorFill (key : ByteArray) (pad : UInt8) (block : Nat) : ByteArray :=
  Id.run do
    let mut out : ByteArray := ByteArray.empty
    for i in [0:block] do
      let kb := if i < key.size then key.get! i else 0
      out := out.push (xorByte kb pad)
    pure out

def hmacSha256 (key msg : ByteArray) : ByteArray :=
  let block := 64
  let k := padKey key block
  let ipad := xorFill k 0x36 block
  let opad := xorFill k 0x5c block
  sha256 (opad ++ sha256 (ipad ++ msg))

def hmacSha256Hex (key msg : String) : String :=
  bytesHex (hmacSha256 key.toUTF8 msg.toUTF8)

theorem hmac_sha256_rfc4231_case1 :
    hmacSha256Hex
      (String.ofList (List.replicate 20 (Char.ofNat 0x0b)))
      "Hi There" =
      "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7" := by
  native_decide

end NuropbRmq.Crypto
