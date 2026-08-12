# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Invoice extract mesh worker (idempotent by document_id).

Run first (with RabbitMQ up)::

    uv run --project examples/langgraph_example python examples/langgraph_example/worker.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

# Allow running as ``python examples/langgraph_example/worker.py``
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import MESH_EXCHANGE, METHODS, SERVICE_NAME, cfg, routing_key  # noqa: E402
from sample_invoices import extract_fields  # noqa: E402

from nuropb_rmq import MeshService, RpcServer, ServiceIdentity  # noqa: E402


async def main() -> None:
    config = cfg()
    mesh = MeshService(
        config,
        identity=ServiceIdentity(SERVICE_NAME),
        methods=list(METHODS),
        exchange=MESH_EXCHANGE,
    )
    # Idempotency cache: at-least-once mesh / LangGraph replay may re-deliver.
    cache: dict[str, dict[str, Any]] = {}

    async def handler(method: str, params: object) -> object:
        if method != routing_key("extract"):
            raise ValueError(f"unknown method: {method}")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        document_id = params.get("document_id")
        raw_text = params.get("raw_text")
        doc_type = params.get("doc_type")
        if not isinstance(document_id, str) or not document_id:
            raise ValueError("document_id must be a non-empty string")
        if not isinstance(raw_text, str):
            raise ValueError("raw_text must be a string")
        if not isinstance(doc_type, str):
            raise ValueError("doc_type must be a string")

        # Simulate slow remote OCR/extract so reconnect demos can interrupt mid-call.
        # Sleep even on cache hit so a replay/duplicate still has an in-flight window.
        await asyncio.sleep(0.5)
        cached = cache.get(document_id)
        if cached is not None:
            print(
                f"[worker] extract document_id={document_id!r} (idempotent cache hit)",
                flush=True,
            )
            return dict(cached)

        result = extract_fields(document_id, raw_text, doc_type)
        cache[document_id] = result
        print(
            f"[worker] extract document_id={document_id!r} "
            f"vendor={result['vendor']!r} total={result['total']}",
            flush=True,
        )
        return result

    server: RpcServer | None = None
    stop = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: _request_stop())

    try:
        await mesh.start()
        server = RpcServer.from_mesh(mesh, handler=handler)
        await server.start()
        print(
            f"[worker] listening identity={SERVICE_NAME!r} methods={list(METHODS)} "
            f"mesh={MESH_EXCHANGE!r} (Ctrl-C to stop)",
            flush=True,
        )
        await stop.wait()
    finally:
        stop.set()
        if server is not None:
            await server.close()
        await mesh.close()
        print("[worker] stopped", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
