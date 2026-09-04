# Interop hello (Lean ↔ Python)

Durable queue `nr.interop.hello`. Mix languages:

```bash
# Terminal 1
uv run python examples/interop_hello/consumer.py
# or: lake exe interop_hello_consumer

# Terminal 2
lake exe interop_hello_publisher
# or: uv run python examples/interop_hello/publisher.py
```

Needs RabbitMQ (`NUROPB_RMQ_HOST` / `NUROPB_RMQ_PORT`). Lean client: `import NuropbRMQ`.
