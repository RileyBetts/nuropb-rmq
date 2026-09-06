/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import Common
import NuropbRMQ

open Std.Async
open NuropbRMQ

def main : IO Unit := Examples.Common.runAsync do
  let cfg ← liftM Examples.Common.cfg
  let sub ← EventSubscriber.start cfg "nr.ex.lean.events" "fanout"
  let pub ← EventPublisher.start cfg "nr.ex.lean.events" "fanout"
  EventPublisher.publish pub "" "lean.coverage.ping" (.obj [("ok", .bool true)])
  let (meth, _) ← EventSubscriber.receive sub 8000
  if meth != "lean.coverage.ping" then
    throw (IO.userError s!"unexpected event '{meth}'")
  liftM (IO.println "events: ok")
  EventPublisher.close pub
  EventSubscriber.close sub
