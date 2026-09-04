# Interop mesh (Lean ↔ Python)

Service identity `interop` on `nr.mesh`, events on `nr.interop.events`.

```bash
# Terminal 1 — one service
uv run python examples/interop_mesh/service.py
# or: lake exe interop_mesh_service

# Terminal 2 — the other language
lake exe interop_mesh_client
# or: uv run python examples/interop_mesh/client.py
```

Expected: `interop.ping` / `interop.echo` RPC and an `interop.request_handled` event.
Lean apps: `require NuropbRMQ` then `import NuropbRMQ`.
