/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

/-!
Computable SHA-256 (FIPS 180-4). Used by HMAC-SHA256 JWT verify.
Not a cryptographic hardness proof.
-/

namespace NuropbRmq.Crypto

def rotR (x : UInt32) (n : Nat) : UInt32 :=
  let n := n % 32
  (x >>> UInt32.ofNat n) ||| (x <<< UInt32.ofNat ((32 - n) % 32))

def ch (x y z : UInt32) : UInt32 := (x &&& y) ^^^ ((~~~x) &&& z)
def maj (x y z : UInt32) : UInt32 := (x &&& y) ^^^ (x &&& z) ^^^ (y &&& z)
def capSigma0 (x : UInt32) : UInt32 := rotR x 2 ^^^ rotR x 13 ^^^ rotR x 22
def capSigma1 (x : UInt32) : UInt32 := rotR x 6 ^^^ rotR x 11 ^^^ rotR x 25
def sigma0 (x : UInt32) : UInt32 := rotR x 7 ^^^ rotR x 18 ^^^ (x >>> 3)
def sigma1 (x : UInt32) : UInt32 := rotR x 17 ^^^ rotR x 19 ^^^ (x >>> 10)

def K : Array UInt32 := #[
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]

def H0 : Array UInt32 := #[
  0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
]

def load32be (b : ByteArray) (i : Nat) : UInt32 :=
  (b.get! i).toUInt32 <<< 24 |||
  (b.get! (i+1)).toUInt32 <<< 16 |||
  (b.get! (i+2)).toUInt32 <<< 8 |||
  (b.get! (i+3)).toUInt32

def store32be (x : UInt32) : Array UInt8 :=
  #[ (x >>> 24).toUInt8, (x >>> 16).toUInt8, (x >>> 8).toUInt8, x.toUInt8 ]

partial def padZeroTo56 (a : ByteArray) : ByteArray :=
  if a.size % 64 = 56 then a else padZeroTo56 (a.push 0)

def appendUInt64BE (a : ByteArray) (n : UInt64) : ByteArray :=
  let rec go (acc : ByteArray) (shift : Nat) : ByteArray :=
    match shift with
    | 0 => acc.push (UInt64.toUInt8 n)
    | s+1 =>
        let b := UInt64.toUInt8 (n >>> UInt64.ofNat (8 * (s+1)))
        go (acc.push b) s
  go a 7

def pad (msg : ByteArray) : ByteArray :=
  let bitLen : UInt64 := UInt64.ofNat (msg.size * 8)
  appendUInt64BE (padZeroTo56 (msg.push 0x80)) bitLen

def schedule (block : ByteArray) : Array UInt32 :=
  Id.run do
    let mut w : Array UInt32 := Array.replicate 64 0
    for i in [0:16] do
      w := w.set! i (load32be block (i * 4))
    for i in [16:64] do
      let v := sigma1 w[i-2]! + w[i-7]! + sigma0 w[i-15]! + w[i-16]!
      w := w.set! i v
    pure w

def compress (h : Array UInt32) (block : ByteArray) : Array UInt32 :=
  let w := schedule block
  Id.run do
    let mut a := h[0]!; let mut b := h[1]!; let mut c := h[2]!; let mut d := h[3]!
    let mut e := h[4]!; let mut f := h[5]!; let mut g := h[6]!; let mut hh := h[7]!
    for i in [0:64] do
      let t1 := hh + capSigma1 e + ch e f g + K[i]! + w[i]!
      let t2 := capSigma0 a + maj a b c
      hh := g; g := f; f := e; e := d + t1
      d := c; c := b; b := a; a := t1 + t2
    pure #[ h[0]!+a, h[1]!+b, h[2]!+c, h[3]!+d, h[4]!+e, h[5]!+f, h[6]!+g, h[7]!+hh ]

partial def hashBlocks (h : Array UInt32) (padded : ByteArray) (off : Nat) : Array UInt32 :=
  if off + 64 > padded.size then h
  else
    let block := padded.extract off (off + 64)
    hashBlocks (compress h block) padded (off + 64)

def sha256 (msg : ByteArray) : ByteArray :=
  let h := hashBlocks H0 (pad msg) 0
  Id.run do
    let mut out : ByteArray := ByteArray.empty
    for i in [0:8] do
      for b in store32be h[i]! do
        out := out.push b
    pure out

def hexDigit (n : Nat) : Char :=
  if n < 10 then Char.ofNat ('0'.toNat + n) else Char.ofNat ('a'.toNat + (n - 10))

def byteHex (b : UInt8) : String :=
  String.ofList [hexDigit (b.toNat / 16), hexDigit (b.toNat % 16)]

def bytesHex (b : ByteArray) : String :=
  Id.run do
    let mut s := ""
    for i in [0:b.size] do
      s := s ++ byteHex (b.get! i)
    pure s

def sha256Hex (s : String) : String := bytesHex (sha256 s.toUTF8)

theorem sha256_empty :
    sha256Hex "" = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" := by
  native_decide

theorem sha256_abc :
    sha256Hex "abc" = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" := by
  native_decide

end NuropbRmq.Crypto
