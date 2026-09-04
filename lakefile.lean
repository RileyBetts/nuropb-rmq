/-
Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
Released under Apache 2.0 license as described in the file LICENSE.
-/
import Lake
open System Lake DSL

package «NuropbRMQ» where
  version := v!"0.1.0"

/-- Pure kernels + proofs. Lake target avoids NuropbRmq/NuropbRMQ case clash. -/
@[default_target]
lean_lib «NuropbRMQSpec» where
  srcDir := "specs/lean"
  roots := #[`NuropbRmq]

target socket.o pkg : FilePath := do
  let oFile := pkg.buildDir / "c" / "socket.o"
  let srcJob ← inputTextFile <| pkg.dir / "NuropbRMQ" / "ffi" / "socket.c"
  let weakArgs := #["-I", (← getLeanIncludeDir).toString]
  buildO oFile srcJob weakArgs #["-fPIC"]

/-- PLAIN AMQP client (POSIX sockets). Default target; no OpenSSL. -/
@[default_target]
lean_lib «NuropbRMQ» where
  moreLinkObjs := #[socket.o]

target tls.o pkg : FilePath := do
  let oFile := pkg.buildDir / "c" / "tls.o"
  let srcJob ← inputTextFile <| pkg.dir / "NuropbRMQ" / "ffi" / "tls.c"
  let mut weakArgs := #["-I", (← getLeanIncludeDir).toString]
  for p in ([
    "/opt/homebrew/opt/openssl@3/include",
    "/opt/homebrew/opt/openssl/include",
    "/usr/local/opt/openssl@3/include",
    "/usr/local/opt/openssl/include"
  ] : List FilePath) do
    if (← p.pathExists) then
      weakArgs := weakArgs ++ #["-I", p.toString]
  buildO oFile srcJob weakArgs #["-fPIC"]

/-- Optional AMQPS. Not a default target (Reservoir must not require libssl). -/
lean_lib «NuropbRMQTls» where
  moreLinkObjs := #[tls.o]
  moreLinkArgs := #[
    "-L/opt/homebrew/opt/openssl@3/lib",
    "-L/opt/homebrew/opt/openssl/lib",
    "-L/usr/local/opt/openssl@3/lib",
    "-L/usr/local/opt/openssl/lib",
    "-lssl", "-lcrypto"
  ]

lean_exe oracle where
  root := `Oracle

/-- Shared example config (`import Common`). Not a default Reservoir target. -/
lean_lib «ExampleCommon» where
  srcDir := "examples"
  roots := #[`Common]

/-- Lean examples live under `examples/` (same tree as Python interop scripts). -/
lean_exe lean_hello_publisher where
  srcDir := "examples"
  root := `LeanHello.Publisher

lean_exe lean_hello_consumer where
  srcDir := "examples"
  root := `LeanHello.Consumer

lean_exe lean_mesh_service where
  srcDir := "examples"
  root := `LeanMesh.Service

lean_exe lean_mesh_client where
  srcDir := "examples"
  root := `LeanMesh.Client

lean_exe lean_claims_service where
  srcDir := "examples"
  root := `LeanClaims.Service

lean_exe lean_claims_client where
  srcDir := "examples"
  root := `LeanClaims.Client

lean_exe lean_events_hello where
  srcDir := "examples"
  root := `LeanEvents.Hello

lean_exe lean_dlq_hello where
  srcDir := "examples"
  root := `LeanDlq.Hello

lean_exe lean_reconnect_client where
  srcDir := "examples"
  root := `LeanReconnect.Client

lean_exe interop_hello_publisher where
  srcDir := "examples"
  root := `InteropHello.Publisher

lean_exe interop_hello_consumer where
  srcDir := "examples"
  root := `InteropHello.Consumer

lean_exe interop_mesh_service where
  srcDir := "examples"
  root := `InteropMesh.Service

lean_exe interop_mesh_client where
  srcDir := "examples"
  root := `InteropMesh.Client

/-- Live reply-forge 403 smoke. POSIX only (no OpenSSL). -/
lean_exe lean_reply_acl where
  srcDir := "examples"
  root := `LeanReplyAcl.Hello

/-- tls-verify-full smoke. Not a default target. -/
lean_exe lean_amqps_hello where
  srcDir := "examples"
  root := `LeanAmqps.Hello
  moreLinkArgs := #[
    "-L/opt/homebrew/opt/openssl@3/lib",
    "-L/opt/homebrew/opt/openssl/lib",
    "-L/usr/local/opt/openssl@3/lib",
    "-L/usr/local/opt/openssl/lib",
    "-lssl", "-lcrypto"
  ]

/-- mTLS + SASL EXTERNAL smoke. Not a default target. -/
lean_exe lean_amqps_mtls where
  srcDir := "examples"
  root := `LeanAmqps.Mtls
  moreLinkArgs := #[
    "-L/opt/homebrew/opt/openssl@3/lib",
    "-L/opt/homebrew/opt/openssl/lib",
    "-L/usr/local/opt/openssl@3/lib",
    "-L/usr/local/opt/openssl/lib",
    "-lssl", "-lcrypto"
  ]
