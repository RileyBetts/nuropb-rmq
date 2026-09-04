/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/

import NuropbRmq.Protocol.Bytes
import NuropbRmq.Protocol.Frame
import NuropbRmq.Protocol.ConnectionSM
import NuropbRmq.Pattern.Mesh
import NuropbRmq.Pattern.Jwt

/-!
Pure oracle: check golden vectors with spec kernels. No sockets.
-/

def fail (msg : String) : IO UInt32 := do
  IO.eprintln msg
  return 1

def checkFrames (path : System.FilePath) : IO Bool := do
  let text ← IO.FS.readFile path
  let mut ok := true
  for line in text.splitOn "\n" do
    if line.isEmpty then continue
    let parts := line.splitOn " "
    if parts.length < 2 then continue
    let name := parts[0]!
    match NuropbRmq.Protocol.Bytes.fromHex parts[1]! with
    | none =>
      IO.eprintln s!"{name}: bad hex"
      ok := false
    | some raw =>
      match NuropbRmq.Protocol.decodeFrame raw with
      | none =>
        IO.eprintln s!"{name}: decodeFrame failed"
        ok := false
      | some (fr, _) =>
        match NuropbRmq.Protocol.encodeFrame fr with
        | none =>
          IO.eprintln s!"{name}: encodeFrame failed"
          ok := false
        | some again =>
          if NuropbRmq.Protocol.Bytes.toHex again != NuropbRmq.Protocol.Bytes.toHex raw then
            IO.eprintln s!"{name}: roundtrip mismatch"
            ok := false
  return ok

def applyEvent (s : NuropbRmq.Protocol.State) (tok : String) : Option NuropbRmq.Protocol.State :=
  open NuropbRmq.Protocol in
  if tok == "tcpConnected:false" then tryStep s (.tcpConnected false)
  else if tok == "tcpConnected:true" then tryStep s (.tcpConnected true)
  else if tok == "tlsVerified" then tryStep s .tlsVerified
  else if tok == "amqpHeader" then tryStep s .amqpHeader
  else if tok == "connStart" then tryStep s .connStart
  else if tok == "startOk" then tryStep s .startOk
  else if tok == "tune" then tryStep s .tune
  else if tok == "tuneOk:60" then tryStep s (.tuneOk 60)
  else if tok == "open" then tryStep s .open
  else if tok == "openOk" then tryStep s .openOk
  else none

def checkTrace (path : System.FilePath) : IO Bool := do
  let text ← IO.FS.readFile path
  let mut s : NuropbRmq.Protocol.State := {}
  for line in text.splitOn "\n" do
    if line.isEmpty then continue
    if line.startsWith "final:" then
      let want := line.drop 6
      return decide (toString (repr s.conn) == want ||
        (want == "openOk" && s.conn == NuropbRmq.Protocol.ConnState.openOk))
    match applyEvent s line with
    | none =>
      IO.eprintln s!"sm reject at {line}"
      return false
    | some s' => s := s'
  return true

def checkAcl (path : System.FilePath) : IO Bool := do
  let text ← IO.FS.readFile path
  let mut ok := true
  for line in text.splitOn "\n" do
    if line.isEmpty then continue
    let p := line.splitOn " "
    if p.length < 4 then continue
    let got := NuropbRmq.Pattern.Mesh.tryBind p[1]! p[2]!
    let exp := p[3]!
    let okRow :=
      (exp == "bindOk" && got == .bindOk) ||
      (exp == "bindRefused" && got == .bindRefused)
    if !okRow then
      IO.eprintln s!"acl mismatch {line}"
      ok := false
  return ok

def main (args : List String) : IO UInt32 := do
  let root := match args with | r :: _ => r | [] => "."
  let frames := System.FilePath.mk root / "specs" / "vectors" / "frames.txt"
  let trace := System.FilePath.mk root / "specs" / "vectors" / "sm_trace.txt"
  let traceTls := System.FilePath.mk root / "specs" / "vectors" / "sm_trace_tls.txt"
  let acl := System.FilePath.mk root / "specs" / "vectors" / "acl.txt"
  let mut ok := true
  if !(← checkFrames frames) then ok := false
  if !(← checkTrace trace) then ok := false
  if !(← checkTrace traceTls) then ok := false
  if !(← checkAcl acl) then ok := false
  let jwt := NuropbRmq.Pattern.Jwt.verifyHs256
    "test-secret" NuropbRmq.Pattern.Jwt.goldenToken 1700000000 "corr-id-01" "orders.ping" false
  if jwt != .authOk then
    IO.eprintln "jwt golden failed"
    ok := false
  if ok then
    IO.println "oracle: ok"
    return 0
  return 1
