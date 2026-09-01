"""Reconnect demo: drop client connection mid remote extract; park-and-retry.

Default Session policy parks the in-flight RPC and republishes after a new
epoch. Requires the worker running first.

    uv run --project examples/langgraph_example python examples/langgraph_example/worker.py
    uv run --project examples/langgraph_example python examples/langgraph_example/reconnect_demo.py

Fail-fast (`Session(..., fail_outstanding=True)`) still maps to LangGraph
checkpoint replay via ``RetriableRemoteError`` in ``adapter.py``.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EXTRACT_READS,
    EXTRACT_WRITES,
    MESH_EXCHANGE,
    SERVICE_NAME,
    cfg,
)
from adapter import remote_node  # noqa: E402
from sample_invoices import DEFAULT_DOCUMENT_ID  # noqa: E402

from langgraph.graph import END, START, StateGraph  # noqa: E402
from nuropb_rmq import RpcClient, Session  # noqa: E402

from graph import InvoiceState, classify, ingest, validate  # noqa: E402


async def main() -> None:
    document_id = DEFAULT_DOCUMENT_ID
    session = Session(cfg())
    await session.start()
    client = RpcClient(session)
    start_epoch = session.epoch

    extract = remote_node(
        client,
        service=SERVICE_NAME,
        method="extract",
        reads=EXTRACT_READS,
        writes=EXTRACT_WRITES,
        exchange=MESH_EXCHANGE,
    )

    async def extract_node(state: InvoiceState) -> dict[str, Any]:
        print(
            f"[reconnect] extract (remote) document_id={state.get('document_id')!r}",
            flush=True,
        )

        async def _force_drop() -> None:
            await asyncio.sleep(0.15)
            print("[reconnect] forcing client disconnect mid-call", flush=True)
            reader = session.conn._reader_task
            await session.conn.force_drop()
            if reader is not None and reader.done():
                try:
                    _ = reader.exception()
                except (asyncio.CancelledError, asyncio.InvalidStateError):
                    pass

        asyncio.create_task(_force_drop(), name="force-drop")
        return await extract(dict(state))

    g = StateGraph(InvoiceState)
    g.add_node("ingest", ingest)
    g.add_node("classify", classify)
    g.add_node("extract", extract_node)
    g.add_node("validate", validate)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_edge("classify", "extract")
    g.add_edge("extract", "validate")
    g.add_edge("validate", END)
    app = g.compile()

    try:
        result = await app.ainvoke({"document_id": document_id})
        if session.epoch <= start_epoch:
            raise RuntimeError("expected park-and-retry to bump session epoch")
        print(
            f"[reconnect] done epoch={session.epoch} valid={result.get('valid')} "
            f"vendor={result.get('vendor')!r} total={result.get('total')}",
            flush=True,
        )
        if not result.get("valid"):
            raise SystemExit(1)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
