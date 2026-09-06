# NuropbRmq Lean specs (Protocol + Session + Pattern)

Lean 4.33 model and proofs of:

- Protocol connection/channel invariants 1–7, `update-secret`, blocked publish,
  heartbeat miss-count
- Publisher confirms, delivery settle, `basic.return` then confirm-ack
- Session correlation (Phase 1b) and park/fail-fast reconnect (Phase 2)
- Pattern mesh bind, fail-closed claims, **executable HS256 JWT**, ACL profiles
- SHA-256 / HMAC (computable; not hardness proofs)
- Executable AMQP frame/method codec and JSON-RPC envelope (used by `NuropbRMQ`)

The Lake **package** is **`NuropbRMQ`** at the **repository root** (Reservoir
requires a root `lake-manifest.json`). This directory is the `srcDir` for the
pure proof library **`NuropbRMQSpec`** (modules stay `NuropbRmq.*`).

```bash
# from repository root — not `cd specs/lean`
lake build NuropbRMQSpec   # proofs only (no FFI / sockets)
lake build NuropbRMQ       # Std.Async.TCP AMQP client (libuv; no OpenSSL)
lake exe oracle .          # golden vectors under specs/vectors/
```

See [CORRESPONDENCE.md](CORRESPONDENCE.md) for Lean ↔ Python mapping and the
Runtime section. See `../specpp/` for the SpeC++ SMT CheckSat gate.

Lean apps:

```text
require NuropbRMQ from git "https://github.com/RileyBetts/nuropb-rmq" @ "<tag>"
```

then `import NuropbRMQ`. Optional AMQPS is `import NuropbRMQTls` /
`NuropbRMQTls.connectAsync` (`lake build NuropbRMQTls`; OpenSSL memory BIO
on the UV loop; not a default target). mTLS PEM or PKCS#12 + SASL `EXTERNAL`,
and RS256/ES256 JWT verify, are supported on that target.
The Python wheel stays `nuropb_rmq` and does not embed Lean FFI.
