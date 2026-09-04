/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRMQ

namespace Examples.Common

def INTEROP_HELLO_QUEUE : String := "nr.interop.hello"
def INTEROP_SERVICE : String := "interop"
def INTEROP_EVENTS : String := "nr.interop.events"
def MESH_EXCHANGE : String := "nr.mesh"

def cfg : IO NuropbRMQ.ConnectionConfig :=
  NuropbRMQ.envConfig

end Examples.Common
