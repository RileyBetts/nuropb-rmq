/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/
import Std.Async

/-!
Bench-only IO slice counters. Off unless `enableIoStats` / `NUROPB_BENCH_IO=1`.
Not a public product API and not an SLO.
-/

open Std.Async

namespace NuropbRMQ

structure IoSliceStats where
  enabled : Bool := false
  encodeNs : Nat := 0
  sendEnqNs : Nat := 0
  aioSendNs : Nat := 0
  recvNs : Nat := 0
  tryReadNs : Nat := 0
  assembleNs : Nat := 0
  offerNs : Nat := 0
  ackNs : Nat := 0
  confirmWaitNs : Nat := 0
  replyWaitNs : Nat := 0
  recvCalls : Nat := 0
  uvWrites : Nat := 0
  refMods : Nat := 0
deriving Inhabited

initialize ioSliceStats : IO.Ref IoSliceStats ← IO.mkRef {}

def ioStatsOn : IO Bool := do
  return (← ioSliceStats.get).enabled

def enableIoStats : IO Unit :=
  ioSliceStats.set { ({} : IoSliceStats) with enabled := true }

def resetIoStats : IO Unit := do
  let s ← ioSliceStats.get
  if s.enabled then
    ioSliceStats.set { enabled := true }

def enableIoStatsFromEnv : IO Unit := do
  match (← IO.getEnv "NUROPB_BENCH_IO") with
  | some "1" | some "true" | some "yes" => enableIoStats
  | _ => pure ()

def addIoNs (f : IoSliceStats → Nat → IoSliceStats) (ns : Nat) : IO Unit := do
  ioSliceStats.modify fun s => if s.enabled then f s ns else s

def bumpIo (f : IoSliceStats → IoSliceStats) : IO Unit := do
  ioSliceStats.modify fun s => if s.enabled then f s else s

def addEncodeNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with encodeNs := s.encodeNs + n }) ns

def addSendEnqNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with sendEnqNs := s.sendEnqNs + n }) ns

def addAioSendNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with aioSendNs := s.aioSendNs + n }) ns

def addRecvNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with recvNs := s.recvNs + n }) ns

def addTryReadNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with tryReadNs := s.tryReadNs + n }) ns

def addAssembleNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with assembleNs := s.assembleNs + n }) ns

def addOfferNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with offerNs := s.offerNs + n }) ns

def addAckNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with ackNs := s.ackNs + n }) ns

def addConfirmWaitNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with confirmWaitNs := s.confirmWaitNs + n }) ns

def addReplyWaitNs (ns : Nat) : IO Unit :=
  addIoNs (fun s n => { s with replyWaitNs := s.replyWaitNs + n }) ns

def bumpRecvCall : IO Unit :=
  bumpIo fun s => { s with recvCalls := s.recvCalls + 1 }

def bumpUvWrite : IO Unit :=
  bumpIo fun s => { s with uvWrites := s.uvWrites + 1 }

def bumpRefMod : IO Unit :=
  bumpIo fun s => { s with refMods := s.refMods + 1 }

/-- Time `act` when stats are on. One `IO.Ref` read when off. -/
def timedIo (add : Nat → IO Unit) (act : IO α) : IO α := do
  if !(← ioStatsOn) then
    act
  else
    let t0 ← IO.monoNanosNow
    let a ← act
    let t1 ← IO.monoNanosNow
    add (t1 - t0)
    return a

def timedAsync (add : Nat → IO Unit) (act : Async α) : Async α := do
  if !(← liftM ioStatsOn) then
    act
  else
    let t0 ← liftM IO.monoNanosNow
    let a ← act
    let t1 ← liftM IO.monoNanosNow
    liftM (add (t1 - t0))
    return a

def formatIoStats (count : Nat) : IO String := do
  let s ← ioSliceStats.get
  let per (ns : Nat) : String :=
    if count == 0 then "0" else toString (ns / count)
  return s!"lean io_slice encode_ns={s.encodeNs} send_enq_ns={s.sendEnqNs} aio_send_ns={s.aioSendNs} recv_ns={s.recvNs} tryread_ns={s.tryReadNs} assemble_ns={s.assembleNs} offer_ns={s.offerNs} ack_ns={s.ackNs} confirm_wait_ns={s.confirmWaitNs} reply_wait_ns={s.replyWaitNs} recv_calls={s.recvCalls} uv_writes={s.uvWrites} ref_mods={s.refMods} per_msg_ns encode={per s.encodeNs} send_enq={per s.sendEnqNs} aio_send={per s.aioSendNs} recv={per s.recvNs} tryread={per s.tryReadNs} assemble={per s.assembleNs} offer={per s.offerNs} ack={per s.ackNs} confirm_wait={per s.confirmWaitNs} reply_wait={per s.replyWaitNs}"

end NuropbRMQ
