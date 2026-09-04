/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import NuropbRmq.Pattern.Envelope
import NuropbRMQ.Connection
import NuropbRMQ.Socket

namespace NuropbRMQ

open Std.Async
open NuropbRmq.Pattern.Envelope

def DEFAULT_REGISTRY_EXCHANGE : String := "nr.mesh.registry"

structure ServiceAdvertisement where
  service : String
  methods : List String
  instanceId : String
  queue : String
  exchange : String
  publishedAt : Nat
  ttlS : Nat
  deriving Repr

def ServiceAdvertisement.toWire (a : ServiceAdvertisement) : ByteArray :=
  utf8 (encodeJson (.obj [
    ("service", .str a.service),
    ("methods", .arr (a.methods.map Json.str)),
    ("instance_id", .str a.instanceId),
    ("queue", .str a.queue),
    ("exchange", .str a.exchange),
    ("published_at", .num a.publishedAt),
    ("ttl_s", .num a.ttlS),
  ]))
where
  utf8 s := s.toUTF8

def ServiceAdvertisement.fromWire (body : ByteArray) : Option ServiceAdvertisement :=
  match decodeMessage body with
  | .error _ => none
  | .ok _ =>
    -- advertisements are not JSON-RPC; parse as generic JSON
    match String.fromUTF8? body >>= parse with
    | none => none
    | some j =>
      match objGet j "service" >>= asStr, objGet j "queue" >>= asStr,
            objGet j "exchange" >>= asStr, objGet j "instance_id" >>= asStr with
      | some svc, some q, some ex, some inst =>
        let methods :=
          match objGet j "methods" with
          | some (.arr xs) => xs.filterMap asStr
          | _ => []
        let publishedAt := match objGet j "published_at" with | some (.num n) => n.toNat | _ => 0
        let ttlS := match objGet j "ttl_s" with | some (.num n) => n.toNat | _ => 60
        some { service := svc, methods, instanceId := inst, queue := q, exchange := ex,
               publishedAt, ttlS }
      | _, _, _, _ => none

def MeshRegistryPublisher.announce (c : AmqpConnection) (channelId : Nat)
    (advert : ServiceAdvertisement) (exchange : String := DEFAULT_REGISTRY_EXCHANGE) : Async Unit := do
  exchangeDeclare c channelId exchange "fanout" (durable := true)
  basicPublishAsync c channelId advert.toWire exchange "" { contentType := some "application/json" }

structure MeshRegistryViewer where
  conn : AmqpConnection
  store : IO.Ref (List ServiceAdvertisement)
  channelId : Nat := 1

def MeshRegistryViewer.start (cfg : ConnectionConfig)
    (exchange : String := DEFAULT_REGISTRY_EXCHANGE)
    (dial : ConnectionConfig → Async AmqpConnection := defaultDial) : Async MeshRegistryViewer := do
  let c ← dial cfg
  let _ ← openChannel c 1
  exchangeDeclare c 1 exchange "fanout" (durable := true)
  let q ← queueDeclare c 1 "" (exclusive := true) (autoDelete := true)
  queueBind c 1 q exchange ""
  let _ ← basicConsume c 1 q
  return { conn := c, store := ← ioRun (IO.mkRef []) }

def MeshRegistryViewer.close (v : MeshRegistryViewer) : Async Unit :=
  NuropbRMQ.close v.conn

def MeshRegistryViewer.pump (v : MeshRegistryViewer) : Async Unit := do
  try
    let msg ← receiveAsync v.conn 100
    basicAckAsync v.conn v.channelId msg.deliveryTag
    if let some a := ServiceAdvertisement.fromWire msg.body then
      ioRun (v.store.modify fun xs => a :: xs.filter (fun x => x.service != a.service))
  catch _ => pure ()

def MeshRegistryViewer.lookup (v : MeshRegistryViewer) (service : String) :
    Async (Option ServiceAdvertisement) := do
  MeshRegistryViewer.pump v
  let now := (← ioRun IO.monoMsNow) / 1000
  let xs := (← ioRun (v.store.get : IO (List ServiceAdvertisement))).filter
    (fun a => a.publishedAt + a.ttlS > now)
  ioRun (v.store.set xs)
  return xs.find? (fun a => a.service == service)

end NuropbRMQ
