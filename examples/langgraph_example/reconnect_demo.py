# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Reconnect demo: drop client connection mid remote extract → rebind → replay.

Requires the worker running first. Only the *client* connection is dropped;
mesh redelivery vs LangGraph replay stay mutually exclusive (reply queue gone).

    uv run --project examples/langgraph_example python examples/langgraph_example/worker.py
    uv run --project examples/langgraph_example python examples/langgraph_example/reconnect_demo.py
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
from adapter import RetriableRemoteError, remote_node  # noqa: E402
from sample_invoices import DEFAULT_DOCUMENT_ID  # noqa: E402

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langgraph.types import RetryPolicy  # noqa: E402
from nuropb_rmq import RpcClient, Session  # noqa: E402

from graph import InvoiceState, classify, ingest, validate  # noqa: E402


async def main() -> None:
    document_id = DEFAULT_DOCUMENT_ID
    session = Session(cfg())
    await session.start()
    client = RpcClient(session)

    rebound = asyncio.Event()
    drop_armed = True

    async def on_connection_lost() -> None:
        print("[reconnect] CONNECTION_LOST — rebinding session", flush=True)
        await session.reconnect()
        rebound.set()
        print("[reconnect] rebound (fresh reply queue / epoch)", flush=True)

    extract = remote_node(
        client,
        service=SERVICE_NAME,
        method="extract",
        reads=EXTRACT_READS,
        writes=EXTRACT_WRITES,
        exchange=MESH_EXCHANGE,
        on_connection_lost=on_connection_lost,
    )

    async def extract_node(state: InvoiceState) -> dict[str, Any]:
        nonlocal drop_armed
        print(
            f"[reconnect] extract (remote) document_id={state.get('document_id')!r}",
            flush=True,
        )
        if drop_armed:
            drop_armed = False

            async def _force_drop() -> None:
                # Worker sleeps ~0.5s; drop while the RPC future is outstanding.
                await asyncio.sleep(0.15)
                print(
                    "[reconnect] forcing client disconnect mid-call",
                    flush=True,
                )
                reader = session.conn._reader_task
                await session.conn.force_drop()
                # Retrieve exception if the read loop lost the race to EOF
                # before cancel (avoids "Task exception was never retrieved").
                if reader is not None and reader.done():
                    try:
                        _ = reader.exception()
                    except (asyncio.CancelledError, asyncio.InvalidStateError):
                        pass

            asyncio.create_task(_force_drop(), name="force-drop")
        else:
            print("[reconnect] replay extract (fresh correlation id)", flush=True)

        return await extract(dict(state))

    g = StateGraph(InvoiceState)
    g.add_node("ingest", ingest)
    g.add_node("classify", classify)
    g.add_node(
        "extract",
        extract_node,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_interval=0.2,
            backoff_factor=1.5,
            retry_on=RetriableRemoteError,
        ),
    )
    g.add_node("validate", validate)
    g.add_edge(START, "ingest")
    g.add_edge("ingest", "classify")
    g.add_edge("classify", "extract")
    g.add_edge("extract", "validate")
    g.add_edge("validate", END)
    app = g.compile(checkpointer=MemorySaver())

    try:
        result = await app.ainvoke(
            {"document_id": document_id},
            config={"configurable": {"thread_id": f"reconnect-{document_id}"}},
        )
        if not rebound.is_set():
            raise RuntimeError("expected CONNECTION_LOST + rebound during demo")
        print(
            f"[reconnect] done valid={result.get('valid')} "
            f"vendor={result.get('vendor')!r} total={result.get('total')}",
            flush=True,
        )
        if not result.get("valid"):
            raise SystemExit(1)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
