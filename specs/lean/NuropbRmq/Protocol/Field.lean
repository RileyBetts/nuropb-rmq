/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.Bytes
import NuropbRmq.Protocol.Frame

/-!
AMQP field tables / shortstr / longstr (subset used by nuropb-rmq).
-/

namespace NuropbRmq.Protocol

open Bytes

inductive FieldVal where
  | null
  | bool (b : Bool)
  | int (n : Int)
  | longstr (s : String)
  | bytes (b : ByteArray)
  | table (t : List (String × FieldVal))

abbrev Table := List (String × FieldVal)

def encodeShortstr (s : String) : Option ByteArray :=
  let raw := utf8 s
  if raw.size > 255 then none
  else some ((ByteArray.empty.push (UInt8.ofNat raw.size)) ++ raw)

def decodeShortstr (data : ByteArray) (off : Nat) : Option (String × Nat) :=
  match getU8 data off with
  | none => none
  | some (n, off') =>
    match slice data off' n.toNat with
    | none => none
    | some raw =>
      match fromUtf8 raw with
      | none => none
      | some s => some (s, off' + n.toNat)

def encodeLongstrBytes (raw : ByteArray) : ByteArray :=
  pushU32be ByteArray.empty raw.size ++ raw

def encodeLongstr (s : String) : ByteArray :=
  encodeLongstrBytes (utf8 s)

def decodeLongstr (data : ByteArray) (off : Nat) : Option (ByteArray × Nat) :=
  match getU32be data off with
  | none => none
  | some (n, off') =>
    if n > defaultFrameMax then none
    else
      match slice data off' n with
      | none => none
      | some raw => some (raw, off' + n)

mutual
  partial def encodeFieldVal (v : FieldVal) (depth maxDepth : Nat) : Option ByteArray :=
    if depth > maxDepth then none
    else
      match v with
      | .null => some (ByteArray.empty.push 'V'.toNat.toUInt8)
      | .bool b =>
        some ((ByteArray.empty.push 't'.toNat.toUInt8).push (if b then 1 else 0))
      | .int n =>
        if -0x80000000 ≤ n ∧ n ≤ 0x7fffffff then
          some (pushI32be (ByteArray.empty.push 'I'.toNat.toUInt8) n)
        else none
      | .longstr s =>
        some ((ByteArray.empty.push 'S'.toNat.toUInt8) ++ encodeLongstr s)
      | .bytes b =>
        some ((ByteArray.empty.push 'x'.toNat.toUInt8) ++ encodeLongstrBytes b)
      | .table t =>
        match encodeTable t (depth + 1) maxDepth with
        | none => none
        | some body => some ((ByteArray.empty.push 'F'.toNat.toUInt8) ++ body)

  partial def encodeTable (t : Table) (depth maxDepth : Nat := defaultMaxTableDepth) : Option ByteArray :=
    if depth > maxDepth then none
    else
      Id.run do
        let mut parts := ByteArray.empty
        for (k, v) in t do
          match encodeShortstr k, encodeFieldVal v depth maxDepth with
          | some ks, some vs => parts := parts ++ ks ++ vs
          | _, _ => return none
        return some (pushU32be ByteArray.empty parts.size ++ parts)

  partial def decodeFieldVal (data : ByteArray) (off depth maxDepth : Nat) : Option (FieldVal × Nat) :=
    if depth > maxDepth then none
    else
      match getU8 data off with
      | none => none
      | some (tag, off') =>
        let c := Char.ofNat tag.toNat
        if c == 'V' then some (.null, off')
        else if c == 't' then
          match getU8 data off' with
          | none => none
          | some (b, o) => some (.bool (b != 0), o)
        else if c == 'I' then
          match getI32be data off' with
          | none => none
          | some (n, o) => some (.int n, o)
        else if c == 'S' then
          match decodeLongstr data off' with
          | none => none
          | some (raw, o) =>
            match fromUtf8 raw with
            | none => none
            | some s => some (.longstr s, o)
        else if c == 'x' then
          match decodeLongstr data off' with
          | none => none
          | some (raw, o) => some (.bytes raw, o)
        else if c == 'F' then
          match decodeTable data off' (depth + 1) maxDepth with
          | none => none
          | some (t, o) => some (.table t, o)
        else if c == 's' then
          match decodeShortstr data off' with
          | none => none
          | some (s, o) => some (.longstr s, o)
        else none

  partial def decodeTable (data : ByteArray) (off : Nat)
      (depth : Nat := 0) (maxDepth : Nat := defaultMaxTableDepth) : Option (Table × Nat) :=
    if depth > maxDepth then none
    else
      match getU32be data off with
      | none => none
      | some (n, off') =>
        if n > defaultFrameMax then none
        else
          let start := off'
          let endPos := start + n
          if endPos > data.size then none
          else
            Id.run do
              let mut pos := start
              let mut acc : Table := []
              while pos < endPos do
                match decodeShortstr data pos with
                | none => return none
                | some (k, p1) =>
                  match decodeFieldVal data p1 (depth + 1) maxDepth with
                  | none => return none
                  | some (v, p2) =>
                    acc := acc ++ [(k, v)]
                    pos := p2
              return some (acc, endPos)
end

def tableGet (t : Table) (k : String) : Option FieldVal :=
  match t.find? (fun p => p.1 == k) with
  | some (_, v) => some v
  | none => none

def tableGetStr (t : Table) (k : String) : Option String :=
  match tableGet t k with
  | some (.longstr s) => some s
  | _ => none

end NuropbRmq.Protocol
