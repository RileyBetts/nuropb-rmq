/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.Bytes
import NuropbRmq.Protocol.FrameDecode

/-!
Executable AMQP 0-9-1 frame encode/decode. Invariant 6: payload+8 ≤ frameMax.
-/

namespace NuropbRmq.Protocol

open Bytes

def frameEnd : UInt8 := 0xce
def defaultFrameMax : Nat := 131072
def defaultMaxTableDepth : Nat := 32

inductive FrameKind where
  | method
  | header
  | body
  | heartbeat
  deriving DecidableEq, Repr

def FrameKind.toU8 : FrameKind → UInt8
  | .method => 1
  | .header => 2
  | .body => 3
  | .heartbeat => 8

def FrameKind.ofU8 : UInt8 → Option FrameKind
  | 1 => some .method
  | 2 => some .header
  | 3 => some .body
  | 8 => some .heartbeat
  | _ => none

structure Frame where
  kind : FrameKind
  channel : Nat
  payload : ByteArray

def protocolHeader : ByteArray :=
  ByteArray.mk #[0x41, 0x4d, 0x51, 0x50, 0x00, 0x00, 0x09, 0x01]

def maxFramePayload (frameMax : Nat := defaultFrameMax) : Option Nat :=
  if frameMax < frameOverhead then none else some (frameMax - frameOverhead)

def encodeFrame (f : Frame) (frameMax : Nat := defaultFrameMax) : Option ByteArray :=
  if f.channel > 0xffff then none
  else
    match maxFramePayload frameMax with
    | none => none
    | some payloadMax =>
      if f.payload.size > payloadMax then none
      else if !decodeAccepted f.payload.size 0 frameMax defaultMaxTableDepth then none
      else
        let buf := pushU8 ByteArray.empty f.kind.toU8
        let buf := pushU16be buf f.channel
        let buf := pushU32be buf f.payload.size
        let buf := buf ++ f.payload
        some (buf.push frameEnd)

/-- Decode one frame. Returns frame and next offset. Size is checked before copy. -/
def decodeFrame (data : ByteArray) (frameMax : Nat := defaultFrameMax) (offset : Nat := 0) :
    Option (Frame × Nat) :=
  if data.size - offset < 7 then none
  else
    match FrameKind.ofU8 (data.get! offset), getU16be data (offset + 1), getU32be data (offset + 3) with
    | some kind, some (ch, _), some (size, _) =>
      match maxFramePayload frameMax with
      | none => none
      | some payloadMax =>
        if size > payloadMax then none
        else if !decodeAccepted size 0 frameMax defaultMaxTableDepth then none
        else
          let endPos := offset + 7 + size
          if data.size < endPos + 1 then none
          else if data.get! endPos != frameEnd then none
          else
            match slice data (offset + 7) size with
            | none => none
            | some payload => some ({ kind, channel := ch, payload }, endPos + 1)
    | _, _, _ => none

theorem decodeFrame_rejects_oversize
    (size : Nat)
    (h : defaultFrameMax < size + 8) :
    decodeAccepted size 0 defaultFrameMax defaultMaxTableDepth = false :=
  decodeAccepted_reject_oversize size 0 defaultFrameMax defaultMaxTableDepth h

end NuropbRmq.Protocol
