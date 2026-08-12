# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""LangChain agent demo: call orders.get_status as a mesh service tool.

Requires the worker running first::

    uv run --project examples/langchain_example python examples/langchain_example/worker.py
    uv run --project examples/langchain_example python examples/langchain_example/agent.py --smoke
    uv run --project examples/langchain_example python examples/langchain_example/agent.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    MESH_EXCHANGE,
    SERVICE_NAME,
    TOOL_DESCRIPTION,
    cfg,
    load_dotenv,
)
from adapter import mesh_service_tool  # noqa: E402
from llm import PROVIDERS, make_chat_model, resolve_provider  # noqa: E402
from sample_orders import DEFAULT_ORDER_ID  # noqa: E402
from schema import GetStatusParams  # noqa: E402

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import StructuredTool  # noqa: E402
from nuropb_rmq import RpcClient, Session  # noqa: E402

MAX_ITERATIONS = 4
SYSTEM_HINT = (
    "You are a customer-support assistant. Use the orders_get_status tool to "
    "look up order status. Answer briefly with the status and tracking details "
    "when available. If the tool returns an error observation, explain it "
    "clearly or retry once with a corrected order_id."
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LangChain mesh service-tool agent demo")
    parser.add_argument(
        "--provider",
        choices=PROVIDERS,
        default=None,
        help="LLM provider (default: NUROPB_LLM_PROVIDER or claude)",
    )
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="No LLM: exercise tool validation + mesh RPC directly",
    )
    parser.add_argument(
        "--error-demo",
        action="store_true",
        help="Ask about an unknown order id so the agent sees an error observation",
    )
    parser.add_argument(
        "--order-id",
        default=None,
        help=f"Order id to ask about (default: {DEFAULT_ORDER_ID})",
    )
    return parser.parse_args(argv)


def _user_question(*, error_demo: bool, order_id: str | None) -> str:
    if error_demo:
        bad = order_id or "ORD-9999"
        return f"Customer asks: where is order {bad}?"
    oid = order_id or DEFAULT_ORDER_ID
    return f"Customer asks: where is order {oid}?"


async def _run_smoke(tool: StructuredTool) -> None:
    print("[agent] smoke: good args", flush=True)
    ok = await tool.ainvoke({"order_id": DEFAULT_ORDER_ID})
    print(f"[agent] observation={ok}", flush=True)

    print("[agent] smoke: bad args (extra field → validation observation)", flush=True)
    bad = await tool.ainvoke({"order_id": DEFAULT_ORDER_ID, "extra": True})
    print(f"[agent] observation={bad}", flush=True)
    assert "INVALID_PARAMS" in bad

    print("[agent] smoke: unknown order (service error observation)", flush=True)
    missing = await tool.ainvoke({"order_id": "ORD-9999"})
    print(f"[agent] observation={missing}", flush=True)
    assert '"error": true' in missing.lower() or '"error":true' in missing.lower()
    print("[agent] smoke done", flush=True)


async def _run_agent_loop(
    *,
    tool: StructuredTool,
    provider: str,
    model_name: str | None,
    question: str,
) -> None:
    llm = make_chat_model(provider, model=model_name)
    bound = llm.bind_tools([tool])
    messages: list[Any] = [
        HumanMessage(content=f"{SYSTEM_HINT}\n\n{question}"),
    ]
    print(f"[agent] provider={provider!r} question={question!r}", flush=True)

    for step in range(1, MAX_ITERATIONS + 1):
        print(f"[agent] step={step}", flush=True)
        ai = await bound.ainvoke(messages)
        if not isinstance(ai, AIMessage):
            raise TypeError(f"expected AIMessage, got {type(ai).__name__}")
        messages.append(ai)

        tool_calls = getattr(ai, "tool_calls", None) or []
        if not tool_calls:
            content = ai.content
            if isinstance(content, list):
                content = json.dumps(content, default=str)
            print(f"[agent] final={content}", flush=True)
            return

        for call in tool_calls:
            name = call.get("name") or tool.name
            call_id = call.get("id") or f"call-{step}"
            args = call.get("args") or {}
            print(f"[agent] tool_call name={name!r} args={args!r}", flush=True)
            if name != tool.name:
                observation = json.dumps(
                    {
                        "error": True,
                        "code_name": "UNKNOWN_TOOL",
                        "message": f"unknown tool {name!r}; only {tool.name!r} is available",
                        "retryable": False,
                    }
                )
            else:
                observation = await tool.ainvoke(args)
            print(f"[agent] observation={observation}", flush=True)
            messages.append(
                ToolMessage(content=observation, tool_call_id=call_id, name=tool.name)
            )

    print("[agent] stopped: max iterations reached", flush=True)


async def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    args = _parse_args(argv)
    question = _user_question(error_demo=args.error_demo, order_id=args.order_id)

    session = Session(cfg())
    await session.start()
    client = RpcClient(session)

    async def on_connection_lost() -> None:
        print("[agent] CONNECTION_LOST → session.reconnect()", flush=True)
        await session.reconnect()

    tool = mesh_service_tool(
        client,
        service=SERVICE_NAME,
        method="get_status",
        args_schema=GetStatusParams,
        description=TOOL_DESCRIPTION,
        exchange=MESH_EXCHANGE,
        on_connection_lost=on_connection_lost,
        name="orders_get_status",
    )

    try:
        if args.smoke:
            await _run_smoke(tool)
        else:
            provider = resolve_provider(args.provider)
            await _run_agent_loop(
                tool=tool,
                provider=provider,
                model_name=args.model,
                question=question,
            )
    finally:
        await session.close()
        print("[agent] done", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
