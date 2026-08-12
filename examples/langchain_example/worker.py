# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Orders mesh worker (idempotent get_status by order_id).

Run first (with RabbitMQ up)::

    uv run --project examples/langchain_example python examples/langchain_example/worker.py
"""

from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any

# Allow running as ``python examples/langchain_example/worker.py``
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import MESH_EXCHANGE, METHODS, SERVICE_NAME, cfg, routing_key  # noqa: E402
from sample_orders import lookup_order  # noqa: E402
from schema import GetStatusParams, OrderStatus  # noqa: E402

from nuropb_rmq import MeshService, RpcError, RpcServer, ServiceIdentity  # noqa: E402
from nuropb_rmq.patterns.errors import SERVER_ERROR, make_error_data  # noqa: E402


async def main() -> None:
    config = cfg()
    mesh = MeshService(
        config,
        identity=ServiceIdentity(SERVICE_NAME),
        methods=list(METHODS),
        exchange=MESH_EXCHANGE,
    )
    # Idempotency cache: at-least-once mesh / agent re-call may re-deliver.
    cache: dict[str, dict[str, Any]] = {}
    method_rk = routing_key("get_status")

    async def handler(method: str, params: object) -> object:
        if method != method_rk:
            raise ValueError(f"unknown method: {method}")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")

        try:
            args = GetStatusParams.model_validate(params)
        except Exception as exc:
            raise ValueError(f"invalid params: {exc}") from exc

        cached = cache.get(args.order_id)
        if cached is not None:
            print(
                f"[worker] get_status order_id={args.order_id!r} (idempotent cache hit)",
                flush=True,
            )
            return dict(cached)

        found = lookup_order(args.order_id)
        if found is None:
            print(
                f"[worker] get_status order_id={args.order_id!r} -> not found",
                flush=True,
            )
            raise RpcError(
                code=SERVER_ERROR,
                message=f"order not found: {args.order_id}",
                data=make_error_data(code=SERVER_ERROR, retryable=False, method=method),
            )

        result = OrderStatus.model_validate(found).model_dump(mode="json")
        cache[args.order_id] = result
        print(
            f"[worker] get_status order_id={args.order_id!r} status={result['status']!r}",
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
