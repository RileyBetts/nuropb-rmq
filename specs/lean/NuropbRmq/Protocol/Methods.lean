/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.Bytes
import NuropbRmq.Protocol.Field

/-!
AMQP 0-9-1 method (de)serialization for connection/channel/queue/exchange/basic/confirm.
-/

namespace NuropbRmq.Protocol

open Bytes

def CONNECTION : Nat := 10
def CHANNEL : Nat := 20
def EXCHANGE : Nat := 40
def QUEUE : Nat := 50
def BASIC : Nat := 60
def CONFIRM : Nat := 85

def CONNECTION_START : Nat := 10
def CONNECTION_START_OK : Nat := 11
def CONNECTION_SECURE : Nat := 20
def CONNECTION_TUNE : Nat := 30
def CONNECTION_TUNE_OK : Nat := 31
def CONNECTION_OPEN : Nat := 40
def CONNECTION_OPEN_OK : Nat := 41
def CONNECTION_CLOSE : Nat := 50
def CONNECTION_CLOSE_OK : Nat := 51
def CONNECTION_BLOCKED : Nat := 60
def CONNECTION_UNBLOCKED : Nat := 61
def CONNECTION_UPDATE_SECRET : Nat := 70
def CONNECTION_UPDATE_SECRET_OK : Nat := 71

def CHANNEL_OPEN : Nat := 10
def CHANNEL_OPEN_OK : Nat := 11
def CHANNEL_CLOSE : Nat := 40
def CHANNEL_CLOSE_OK : Nat := 41

def QUEUE_DECLARE : Nat := 10
def QUEUE_DECLARE_OK : Nat := 11
def QUEUE_BIND : Nat := 20
def QUEUE_BIND_OK : Nat := 21

def EXCHANGE_DECLARE : Nat := 10
def EXCHANGE_DECLARE_OK : Nat := 11

def BASIC_QOS : Nat := 10
def BASIC_QOS_OK : Nat := 11
def BASIC_CONSUME : Nat := 20
def BASIC_CONSUME_OK : Nat := 21
def BASIC_CANCEL : Nat := 30
def BASIC_CANCEL_OK : Nat := 31
def BASIC_PUBLISH : Nat := 40
def BASIC_RETURN : Nat := 50
def BASIC_DELIVER : Nat := 60
def BASIC_ACK : Nat := 80
def BASIC_REJECT : Nat := 90
def BASIC_NACK : Nat := 120

def CONFIRM_SELECT : Nat := 10
def CONFIRM_SELECT_OK : Nat := 11

structure Method where
  classId : Nat
  methodId : Nat
  args : Table := []

def argStr (t : Table) (k : String) (dflt : String := "") : String :=
  (tableGetStr t k).getD dflt

def argInt (t : Table) (k : String) (dflt : Int := 0) : Int :=
  match tableGet t k with
  | some (.int n) => n
  | _ => dflt

def argBool (t : Table) (k : String) (dflt : Bool := false) : Bool :=
  match tableGet t k with
  | some (.bool b) => b
  | _ => dflt

def argTable (t : Table) (k : String) : Table :=
  match tableGet t k with
  | some (.table nested) => nested
  | _ => []

def argBytes (t : Table) (k : String) : ByteArray :=
  match tableGet t k with
  | some (.bytes b) => b
  | some (.longstr s) => utf8 s
  | _ => ByteArray.empty

def pushBits (buf : ByteArray) (bits : Nat) : ByteArray :=
  buf.push (UInt8.ofNat (bits &&& 255))

def encodeMethod (m : Method) : Option ByteArray :=
  let cid := m.classId
  let mid := m.methodId
  let a := m.args
  let head := pushU16be (pushU16be ByteArray.empty cid) mid
  if cid == CONNECTION && mid == CONNECTION_START_OK then
    match encodeTable (argTable a "client_properties") 0, encodeShortstr (argStr a "mechanism"),
          encodeShortstr (argStr a "locale" "en_US") with
    | some props, some mech, some locale =>
      some (head ++ props ++ mech ++ encodeLongstrBytes (argBytes a "response") ++ locale)
    | _, _, _ => none
  else if cid == CONNECTION && mid == CONNECTION_TUNE_OK then
    some (pushU16be (pushU32be (pushU16be head (argInt a "channel_max").toNat)
      (argInt a "frame_max").toNat) (argInt a "heartbeat").toNat)
  else if cid == CONNECTION && mid == CONNECTION_OPEN then
    match encodeShortstr (argStr a "virtual_host" "/"),
          encodeShortstr (argStr a "capabilities") with
    | some vh, some cap =>
      some (head ++ vh ++ cap ++ ByteArray.empty.push (if argBool a "insist" then 1 else 0))
    | _, _ => none
  else if cid == CONNECTION && mid == CONNECTION_CLOSE then
    match encodeShortstr (argStr a "reply_text") with
    | some txt =>
      some (pushU16be (pushU16be (head ++ pushU16be ByteArray.empty (argInt a "reply_code" 200).toNat
        ++ txt) (argInt a "class_id").toNat) (argInt a "method_id").toNat)
    | none => none
  else if cid == CONNECTION && mid == CONNECTION_CLOSE_OK then some head
  else if cid == CONNECTION && mid == CONNECTION_UPDATE_SECRET then
    match encodeShortstr (argStr a "reason") with
    | some r => some (head ++ encodeLongstrBytes (argBytes a "new_secret") ++ r)
    | none => none
  else if cid == CHANNEL && mid == CHANNEL_OPEN then
    encodeShortstr (argStr a "out_of_band") |>.map (head ++ ·)
  else if cid == CHANNEL && mid == CHANNEL_OPEN_OK then
    some (head ++ encodeLongstrBytes (argBytes a "channel_id"))
  else if cid == CHANNEL && mid == CHANNEL_CLOSE then
    match encodeShortstr (argStr a "reply_text") with
    | some txt =>
      some (pushU16be (pushU16be (head ++ pushU16be ByteArray.empty (argInt a "reply_code" 200).toNat
        ++ txt) (argInt a "class_id").toNat) (argInt a "method_id").toNat)
    | none => none
  else if cid == CHANNEL && mid == CHANNEL_CLOSE_OK then some head
  else if cid == QUEUE && mid == QUEUE_DECLARE then
    let bits :=
      (if argBool a "passive" then 1 else 0) +
      (if argBool a "durable" then 2 else 0) +
      (if argBool a "exclusive" then 4 else 0) +
      (if argBool a "auto_delete" then 8 else 0) +
      (if argBool a "nowait" then 16 else 0)
    match encodeShortstr (argStr a "queue"), encodeTable (argTable a "arguments") 0 with
    | some q, some args =>
      some (head ++ pushU16be ByteArray.empty (argInt a "ticket").toNat ++ q ++ pushBits ByteArray.empty bits ++ args)
    | _, _ => none
  else if cid == EXCHANGE && mid == EXCHANGE_DECLARE then
    let bits :=
      (if argBool a "passive" then 1 else 0) +
      (if argBool a "durable" then 2 else 0) +
      (if argBool a "auto_delete" then 4 else 0) +
      (if argBool a "internal" then 8 else 0) +
      (if argBool a "nowait" then 16 else 0)
    match encodeShortstr (argStr a "exchange"), encodeShortstr (argStr a "type" "direct"),
          encodeTable (argTable a "arguments") 0 with
    | some ex, some ty, some args =>
      some (head ++ pushU16be ByteArray.empty (argInt a "ticket").toNat ++ ex ++ ty ++
        pushBits ByteArray.empty bits ++ args)
    | _, _, _ => none
  else if cid == QUEUE && mid == QUEUE_BIND then
    match encodeShortstr (argStr a "queue"), encodeShortstr (argStr a "exchange"),
          encodeShortstr (argStr a "routing_key"), encodeTable (argTable a "arguments") 0 with
    | some q, some ex, some rk, some args =>
      some (head ++ pushU16be ByteArray.empty (argInt a "ticket").toNat ++ q ++ ex ++ rk ++
        ByteArray.empty.push (if argBool a "nowait" then 1 else 0) ++ args)
    | _, _, _, _ => none
  else if cid == BASIC && mid == BASIC_PUBLISH then
    let bits := (if argBool a "mandatory" then 1 else 0) + (if argBool a "immediate" then 2 else 0)
    match encodeShortstr (argStr a "exchange"), encodeShortstr (argStr a "routing_key") with
    | some ex, some rk =>
      some (head ++ pushU16be ByteArray.empty (argInt a "ticket").toNat ++ ex ++ rk ++
        pushBits ByteArray.empty bits)
    | _, _ => none
  else if cid == BASIC && mid == BASIC_RETURN then
    match encodeShortstr (argStr a "reply_text"), encodeShortstr (argStr a "exchange"),
          encodeShortstr (argStr a "routing_key") with
    | some txt, some ex, some rk =>
      some (head ++ pushU16be ByteArray.empty (argInt a "reply_code" 312).toNat ++ txt ++ ex ++ rk)
    | _, _, _ => none
  else if cid == BASIC && mid == BASIC_CONSUME then
    let bits :=
      (if argBool a "no_local" then 1 else 0) +
      (if argBool a "no_ack" then 2 else 0) +
      (if argBool a "exclusive" then 4 else 0) +
      (if argBool a "nowait" then 8 else 0)
    match encodeShortstr (argStr a "queue"), encodeShortstr (argStr a "consumer_tag"),
          encodeTable (argTable a "arguments") 0 with
    | some q, some tag, some args =>
      some (head ++ pushU16be ByteArray.empty (argInt a "ticket").toNat ++ q ++ tag ++
        pushBits ByteArray.empty bits ++ args)
    | _, _, _ => none
  else if cid == BASIC && mid == BASIC_ACK then
    some (head ++ pushU64be ByteArray.empty (argInt a "delivery_tag").toNat ++
      ByteArray.empty.push (if argBool a "multiple" then 1 else 0))
  else if cid == BASIC && mid == BASIC_REJECT then
    some (head ++ pushU64be ByteArray.empty (argInt a "delivery_tag").toNat ++
      ByteArray.empty.push (if argBool a "requeue" then 1 else 0))
  else if cid == BASIC && mid == BASIC_NACK then
    let bits := (if argBool a "multiple" then 1 else 0) + (if argBool a "requeue" then 2 else 0)
    some (head ++ pushU64be ByteArray.empty (argInt a "delivery_tag").toNat ++ pushBits ByteArray.empty bits)
  else if cid == BASIC && mid == BASIC_CANCEL then
    match encodeShortstr (argStr a "consumer_tag") with
    | some tag => some (head ++ tag ++ ByteArray.empty.push (if argBool a "nowait" then 1 else 0))
    | none => none
  else if cid == BASIC && mid == BASIC_QOS then
    some (head ++ pushU32be ByteArray.empty (argInt a "prefetch_size").toNat ++
      pushU16be ByteArray.empty (argInt a "prefetch_count").toNat ++
      ByteArray.empty.push (if argBool a "global_" then 1 else 0))
  else if cid == CONFIRM && mid == CONFIRM_SELECT then
    some (head ++ ByteArray.empty.push (if argBool a "nowait" then 1 else 0))
  else none

def decodeMethod (payload : ByteArray) : Option Method :=
  match getU16be payload 0, getU16be payload 2 with
  | some (cid, _), some (mid, _) =>
    let off := 4
    let mk (args : Table) : Method := { classId := cid, methodId := mid, args }
    if cid == CONNECTION && mid == CONNECTION_START then
      match getU8 payload off with
      | none => none
      | some (maj, o1) =>
        match getU8 payload o1 with
        | none => none
        | some (min, o2) =>
          match decodeTable payload o2 with
          | none => none
          | some (props, o3) =>
            match decodeLongstr payload o3 with
            | none => none
            | some (mech, o4) =>
              match decodeLongstr payload o4 with
              | none => none
              | some (loc, _) =>
                some (mk [
                  ("version_major", .int maj.toNat),
                  ("version_minor", .int min.toNat),
                  ("server_properties", .table props),
                  ("mechanisms", .longstr ((fromUtf8 mech).getD "")),
                  ("locales", .longstr ((fromUtf8 loc).getD "")),
                ])
    else if cid == CONNECTION && mid == CONNECTION_TUNE then
      match getU16be payload off, getU32be payload (off + 2), getU16be payload (off + 6) with
      | some (cm, _), some (fm, _), some (hb, _) =>
        some (mk [("channel_max", .int cm), ("frame_max", .int fm), ("heartbeat", .int hb)])
      | _, _, _ => none
    else if cid == CONNECTION && mid == CONNECTION_OPEN_OK then
      match decodeShortstr payload off with
      | some (s, _) => some (mk [("reserved_1", .longstr s)])
      | none => some (mk [])
    else if cid == CONNECTION && mid == CONNECTION_CLOSE then
      match getU16be payload off with
      | none => none
      | some (code, o1) =>
        match decodeShortstr payload o1 with
        | none => none
        | some (txt, o2) =>
          match getU16be payload o2, getU16be payload (o2 + 2) with
          | some (c2, _), some (m2, _) =>
            some (mk [("reply_code", .int code), ("reply_text", .longstr txt),
              ("class_id", .int c2), ("method_id", .int m2)])
          | _, _ => none
    else if cid == CONNECTION && mid == CONNECTION_CLOSE_OK then some (mk [])
    else if cid == CHANNEL && mid == CHANNEL_OPEN_OK then
      match decodeLongstr payload off with
      | some (raw, _) => some (mk [("channel_id", .bytes raw)])
      | none => some (mk [])
    else if cid == CHANNEL && mid == CHANNEL_CLOSE then
      match getU16be payload off with
      | none => none
      | some (code, o1) =>
        match decodeShortstr payload o1 with
        | none => none
        | some (txt, o2) =>
          match getU16be payload o2, getU16be payload (o2 + 2) with
          | some (c2, _), some (m2, _) =>
            some (mk [("reply_code", .int code), ("reply_text", .longstr txt),
              ("class_id", .int c2), ("method_id", .int m2)])
          | _, _ => none
    else if cid == CHANNEL && mid == CHANNEL_CLOSE_OK then some (mk [])
    else if cid == QUEUE && mid == QUEUE_DECLARE_OK then
      match decodeShortstr payload off with
      | none => none
      | some (q, o1) =>
        match getU32be payload o1, getU32be payload (o1 + 4) with
        | some (mc, _), some (cc, _) =>
          some (mk [("queue", .longstr q), ("message_count", .int mc), ("consumer_count", .int cc)])
        | _, _ => none
    else if cid == EXCHANGE && mid == EXCHANGE_DECLARE_OK then some (mk [])
    else if cid == QUEUE && mid == QUEUE_BIND_OK then some (mk [])
    else if cid == BASIC && mid == BASIC_CONSUME_OK then
      match decodeShortstr payload off with
      | some (tag, _) => some (mk [("consumer_tag", .longstr tag)])
      | none => none
    else if cid == BASIC && mid == BASIC_DELIVER then
      match decodeShortstr payload off with
      | none => none
      | some (tag, o1) =>
        match getU64be payload o1 with
        | none => none
        | some (dt, o2) =>
          match getU8 payload o2 with
          | none => none
          | some (red, o3) =>
            match decodeShortstr payload o3 with
            | none => none
            | some (ex, o4) =>
              match decodeShortstr payload o4 with
              | none => none
              | some (rk, _) =>
                some (mk [
                  ("consumer_tag", .longstr tag),
                  ("delivery_tag", .int dt),
                  ("redelivered", .bool (red != 0)),
                  ("exchange", .longstr ex),
                  ("routing_key", .longstr rk),
                ])
    else if cid == BASIC && mid == BASIC_QOS_OK then some (mk [])
    else if cid == BASIC && mid == BASIC_CANCEL_OK then
      match decodeShortstr payload off with
      | some (tag, _) => some (mk [("consumer_tag", .longstr tag)])
      | none => none
    else if cid == BASIC && mid == BASIC_ACK then
      match getU64be payload off with
      | none => none
      | some (dt, o1) =>
        let mult := match getU8 payload o1 with | some (b, _) => b != 0 | none => false
        some (mk [("delivery_tag", .int dt), ("multiple", .bool mult)])
    else if cid == BASIC && mid == BASIC_NACK then
      match getU64be payload off with
      | none => none
      | some (dt, o1) =>
        let bits := match getU8 payload o1 with | some (b, _) => b.toNat | none => 0
        some (mk [("delivery_tag", .int dt), ("multiple", .bool (bits &&& 1 != 0)),
          ("requeue", .bool (bits &&& 2 != 0))])
    else if cid == CONNECTION && mid == CONNECTION_BLOCKED then
      match decodeShortstr payload off with
      | some (r, _) => some (mk [("reason", .longstr r)])
      | none => some (mk [])
    else if cid == CONNECTION && mid == CONNECTION_UNBLOCKED then some (mk [])
    else if cid == CONNECTION && mid == CONNECTION_SECURE then
      match decodeLongstr payload off with
      | some (c, _) => some (mk [("challenge", .bytes c)])
      | none => none
    else if cid == CONNECTION && mid == CONNECTION_UPDATE_SECRET_OK then some (mk [])
    else if cid == BASIC && mid == BASIC_RETURN then
      match getU16be payload off with
      | none => none
      | some (code, o1) =>
        match decodeShortstr payload o1 with
        | none => none
        | some (txt, o2) =>
          match decodeShortstr payload o2 with
          | none => none
          | some (ex, o3) =>
            match decodeShortstr payload o3 with
            | none => none
            | some (rk, _) =>
              some (mk [("reply_code", .int code), ("reply_text", .longstr txt),
                ("exchange", .longstr ex), ("routing_key", .longstr rk)])
    else if cid == CONFIRM && mid == CONFIRM_SELECT_OK then some (mk [])
    else some (mk [])
  | _, _ => none

structure BasicProperties where
  contentType : Option String := none
  contentEncoding : Option String := none
  headers : Table := []
  deliveryMode : Option Nat := none
  priority : Option Nat := none
  correlationId : Option String := none
  replyTo : Option String := none
  expiration : Option String := none
  messageId : Option String := none
  timestamp : Option Nat := none
  type_ : Option String := none
  userId : Option String := none
  appId : Option String := none
  clusterId : Option String := none

def encodeContentHeader (classId bodySize : Nat) (p : BasicProperties) : Option ByteArray :=
  Id.run do
    let mut flags : Nat := 0
    let mut body := ByteArray.empty
    if let some v := p.contentType then
      flags := flags ||| (1 <<< 15)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.contentEncoding then
      flags := flags ||| (1 <<< 14)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if !p.headers.isEmpty then
      flags := flags ||| (1 <<< 13)
      match encodeTable p.headers 0 with | some b => body := body ++ b | none => return none
    if let some v := p.deliveryMode then
      flags := flags ||| (1 <<< 12)
      body := body.push (UInt8.ofNat v)
    if let some v := p.priority then
      flags := flags ||| (1 <<< 11)
      body := body.push (UInt8.ofNat v)
    if let some v := p.correlationId then
      flags := flags ||| (1 <<< 10)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.replyTo then
      flags := flags ||| (1 <<< 9)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.expiration then
      flags := flags ||| (1 <<< 8)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.messageId then
      flags := flags ||| (1 <<< 7)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.timestamp then
      flags := flags ||| (1 <<< 6)
      body := pushU64be body v
    if let some v := p.type_ then
      flags := flags ||| (1 <<< 5)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.userId then
      flags := flags ||| (1 <<< 4)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.appId then
      flags := flags ||| (1 <<< 3)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    if let some v := p.clusterId then
      flags := flags ||| (1 <<< 2)
      match encodeShortstr v with | some b => body := body ++ b | none => return none
    return some (pushU16be (pushU64be (pushU16be (pushU16be ByteArray.empty classId) 0) bodySize) flags ++ body)

def decodeContentHeader (payload : ByteArray) : Option (Nat × Nat × BasicProperties) :=
  if payload.size < 14 then none
  else
    match getU16be payload 0, getU64be payload 4, getU16be payload 12 with
    | some (classId, _), some (bodySize, _), some (flags, _) =>
      Id.run do
        let mut off := 14
        let mut p : BasicProperties := {}
        if flags &&& (1 <<< 15) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with contentType := some s }; off := o
        if flags &&& (1 <<< 14) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with contentEncoding := some s }; off := o
        if flags &&& (1 <<< 13) != 0 then
          match decodeTable payload off with
          | none => return none
          | some (t, o) => p := { p with headers := t }; off := o
        if flags &&& (1 <<< 12) != 0 then
          match getU8 payload off with
          | none => return none
          | some (b, o) => p := { p with deliveryMode := some b.toNat }; off := o
        if flags &&& (1 <<< 11) != 0 then
          match getU8 payload off with
          | none => return none
          | some (b, o) => p := { p with priority := some b.toNat }; off := o
        if flags &&& (1 <<< 10) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with correlationId := some s }; off := o
        if flags &&& (1 <<< 9) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with replyTo := some s }; off := o
        if flags &&& (1 <<< 8) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with expiration := some s }; off := o
        if flags &&& (1 <<< 7) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with messageId := some s }; off := o
        if flags &&& (1 <<< 6) != 0 then
          match getU64be payload off with
          | none => return none
          | some (ts, o) => p := { p with timestamp := some ts }; off := o
        if flags &&& (1 <<< 5) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with type_ := some s }; off := o
        if flags &&& (1 <<< 4) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with userId := some s }; off := o
        if flags &&& (1 <<< 3) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with appId := some s }; off := o
        if flags &&& (1 <<< 2) != 0 then
          match decodeShortstr payload off with
          | none => return none
          | some (s, o) => p := { p with clusterId := some s }; off := o
        return some (classId, bodySize, p)
    | _, _, _ => none

end NuropbRmq.Protocol
