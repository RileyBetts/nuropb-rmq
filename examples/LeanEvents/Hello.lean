/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Common
import NuropbRMQ

open NuropbRMQ

def main : IO Unit := do
  let cfg ← Examples.Common.cfg
  let sub ← EventSubscriber.start cfg "nr.ex.lean.events" "fanout"
  let pub ← EventPublisher.start cfg "nr.ex.lean.events" "fanout"
  EventPublisher.publish pub "" "lean.coverage.ping" (.obj [("ok", .bool true)])
  let (meth, _) ← EventSubscriber.receive sub 8000
  if meth != "lean.coverage.ping" then
    throw (IO.userError s!"unexpected event '{meth}'")
  IO.println "events: ok"
  EventPublisher.close pub
  EventSubscriber.close sub
