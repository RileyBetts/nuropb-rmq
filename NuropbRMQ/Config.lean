/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

namespace NuropbRMQ

structure ConnectionConfig where
  host : String := "127.0.0.1"
  port : UInt16 := 5672
  virtualHost : String := "/"
  username : String := "guest"
  password : String := "guest"
  heartbeat : Nat := 60
  frameMax : Nat := 131072
  tls : Bool := false
  tlsProfile : String := "tls-verify-full"
  caFile : Option String := none
  certFile : Option String := none
  keyFile : Option String := none
  serverHostname : Option String := none
  deriving Repr, Inhabited

def envConfig : IO ConnectionConfig := do
  let host := (← IO.getEnv "NUROPB_RMQ_HOST").getD "127.0.0.1"
  let portS := (← IO.getEnv "NUROPB_RMQ_PORT").getD "5672"
  let user := (← IO.getEnv "NUROPB_RMQ_USER").getD "guest"
  let pass := (← IO.getEnv "NUROPB_RMQ_PASSWORD").getD "guest"
  let vhost := (← IO.getEnv "NUROPB_RMQ_VHOST").getD "/"
  let tlsFlag := (← IO.getEnv "NUROPB_RMQ_TLS").getD ""
  let tlsOn := tlsFlag == "1" || tlsFlag == "true" || tlsFlag == "yes"
  let port := (portS.toNat?.getD 5672).toUInt16
  return {
    host, port, username := user, password := pass, virtualHost := vhost
    tls := tlsOn
    caFile := ← IO.getEnv "NUROPB_RMQ_CA_FILE"
    certFile := ← IO.getEnv "NUROPB_RMQ_CERT_FILE"
    keyFile := ← IO.getEnv "NUROPB_RMQ_KEY_FILE"
    serverHostname := ← IO.getEnv "NUROPB_RMQ_SERVER_HOSTNAME"
  }

end NuropbRMQ
