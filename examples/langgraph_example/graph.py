# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Happy-path LangGraph: local ingest/classify/validate + remote extract.

Requires the worker running first::

    uv run --project examples/langgraph_example python examples/langgraph_example/worker.py
    uv run --project examples/langgraph_example python examples/langgraph_example/graph.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, TypedDict

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    EXTRACT_READS,
    EXTRACT_WRITES,
    MESH_EXCHANGE,
    SERVICE_NAME,
    cfg,
)
from adapter import remote_node  # noqa: E402
from sample_invoices import DEFAULT_DOCUMENT_ID, get_sample  # noqa: E402

from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from nuropb_rmq import RpcClient, Session  # noqa: E402


class InvoiceState(TypedDict, total=False):
    document_id: str
    raw_text: str
    doc_type: str
    vendor: str
    invoice_date: str
    total: float
    currency: str
    line_items: list[dict[str, Any]]
    valid: bool
    errors: list[str]


def ingest(state: InvoiceState) -> dict[str, Any]:
    document_id = state.get("document_id") or DEFAULT_DOCUMENT_ID
    sample = get_sample(document_id)
    print(f"[graph] ingest document_id={document_id!r}", flush=True)
    return {"document_id": document_id, "raw_text": sample["raw_text"]}


def classify(state: InvoiceState) -> dict[str, Any]:
    text = (state.get("raw_text") or "").lstrip()
    doc_type = "receipt" if text.upper().startswith("RECEIPT") else "invoice"
    print(f"[graph] classify doc_type={doc_type!r}", flush=True)
    return {"doc_type": doc_type}


def validate(state: InvoiceState) -> dict[str, Any]:
    errors: list[str] = []
    total = state.get("total")
    line_items = state.get("line_items") or []
    if total is None:
        errors.append("missing total")
    else:
        summed = sum(float(item.get("amount", 0)) for item in line_items)
        if abs(summed - float(total)) > 0.01:
            errors.append(f"line items sum {summed} != total {total}")
    if not state.get("vendor"):
        errors.append("missing vendor")
    ok = not errors
    print(
        f"[graph] validate valid={ok} vendor={state.get('vendor')!r} "
        f"total={state.get('total')} errors={errors}",
        flush=True,
    )
    return {"valid": ok, "errors": errors}


def build_graph(client: RpcClient, *, on_connection_lost=None):
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
        print(f"[graph] extract (remote) document_id={state.get('document_id')!r}", flush=True)
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
    return g.compile(checkpointer=MemorySaver())


async def main() -> None:
    document_id = DEFAULT_DOCUMENT_ID
    if len(sys.argv) > 1:
        document_id = sys.argv[1]

    session = Session(cfg())
    await session.start()
    client = RpcClient(session)
    try:
        app = build_graph(client)
        result = await app.ainvoke(
            {"document_id": document_id},
            config={"configurable": {"thread_id": f"invoice-{document_id}"}},
        )
        print(
            f"[graph] done valid={result.get('valid')} "
            f"vendor={result.get('vendor')!r} total={result.get('total')} "
            f"currency={result.get('currency')!r}",
            flush=True,
        )
        if not result.get("valid"):
            raise SystemExit(1)
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
