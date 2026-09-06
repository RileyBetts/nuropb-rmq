/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import Std.Async
import NuropbRMQ.Config
import NuropbRMQ.AsyncTransport
import NuropbRMQ.Connection
import NuropbRMQTls.AsyncTls
import NuropbRMQTls.Jwt

open Std.Async
open NuropbRMQ

/-!
Optional AMQPS (tls-verify-full) on the UV loop: `Std.Async.TCP` + memory BIO /
`SSL_ERROR_WANT_*`. Build: `lake build NuropbRMQTls` (requires OpenSSL). Not a
default target.
-/

namespace NuropbRMQ.Tls

/-- Dial PLAIN TCP, complete the TLS handshake on the UV loop, then AMQP. -/
def connectAsync (cfg : ConnectionConfig := {}) : Async AmqpConnection := do
  if cfg.tls == false then
    -- AMQPS entry still honors env/config; force the proven TLS SM step.
    pure ()
  let sock ← connectTcpAsync cfg.host cfg.port
  let hn := cfg.serverHostname.getD cfg.host
  let handle ← ioRun (newHandle hn cfg)
  try
    handshakeLoop sock handle
  catch e =>
    try ioRun (closeSsl handle) catch _ => pure ()
    throw e
  let pipe ← ioRun (TlsPipe.new sock handle)
  let aio := tlsTransportAsync pipe
  connectWithAsync { cfg with tls := true } aio (useTls := true)

/-- Dialer value (no default cfg) for `Session.startAsync`. -/
def defaultDial (cfg : ConnectionConfig) : Async AmqpConnection :=
  connectAsync cfg

end NuropbRMQ.Tls

namespace NuropbRMQTls
/-- Alias matching the Lake target / docs. -/
def connectAsync (cfg : NuropbRMQ.ConnectionConfig := {}) :
    Std.Async.Async NuropbRMQ.AmqpConnection :=
  NuropbRMQ.Tls.connectAsync cfg

def defaultDial (cfg : NuropbRMQ.ConnectionConfig) :
    Std.Async.Async NuropbRMQ.AmqpConnection :=
  NuropbRMQ.Tls.defaultDial cfg
end NuropbRMQTls
