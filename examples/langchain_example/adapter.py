# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Thin LangChain adapter: mesh_service_tool over nuropb-rmq RpcClient."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ValidationError

from nuropb_rmq import DEFAULT_MESH_EXCHANGE, RpcClient, RpcError
from nuropb_rmq.patterns.errors import CONNECTION_LOST


def _is_connection_lost(err: RpcError) -> bool:
    if err.code == CONNECTION_LOST:
        return True
    data = err.data
    if isinstance(data, dict) and data.get("code_name") == "CONNECTION_LOST":
        return True
    return False


def _validation_observation(exc: ValidationError) -> str:
    payload = {
        "error": True,
        "code": -32602,
        "code_name": "INVALID_PARAMS",
        "message": "model arguments failed schema validation (reject, not coerce)",
        "retryable": False,
        "details": exc.errors(include_url=False),
    }
    return json.dumps(payload)


def _rpc_error_observation(err: RpcError, *, retryable: bool | None = None) -> str:
    data = err.data if isinstance(err.data, dict) else {}
    if retryable is None:
        retryable = bool(data.get("retryable", False))
    payload = {
        "error": True,
        "code": err.code,
        "code_name": data.get("code_name", "UNKNOWN"),
        "message": err.message,
        "retryable": retryable,
    }
    return json.dumps(payload)


def _result_observation(result: Any) -> str:
    return json.dumps(result, default=str)


def mesh_service_tool(
    client: RpcClient,
    *,
    service: str,
    method: str,
    args_schema: type[BaseModel],
    description: str,
    exchange: str = DEFAULT_MESH_EXCHANGE,
    on_connection_lost: Callable[[], Awaitable[None]] | None = None,
    name: str | None = None,
) -> StructuredTool:
    """Return an async StructuredTool whose invoke is one mesh RPC call.

    One tool maps to exactly one ``service.method``. LLM-supplied arguments are
    validated against ``args_schema`` and rejected (never coerced) before any
    wire request. Errors map to a single tool observation (not a raised
    exception) so the agent loop can react. The adapter never auto-retries
    across correlation ids.
    """
    rk = f"{service}.{method}" if not method.startswith(f"{service}.") else method
    tool_name = name or f"{service}_{method}"

    async def _ainvoke(**kwargs: Any) -> str:
        # LangChain may already have validated; re-validate as the single
        # reject-not-coerce gate before anything hits the wire.
        try:
            model = args_schema.model_validate(kwargs)
        except ValidationError as exc:
            return _validation_observation(exc)

        params = model.model_dump(mode="json")
        try:
            result = await client.request(rk, rk, params, exchange=exchange)
        except RpcError as err:
            if _is_connection_lost(err):
                if on_connection_lost is not None:
                    await on_connection_lost()
                return _rpc_error_observation(err, retryable=True)
            return _rpc_error_observation(err)
        return _result_observation(result)

    def _on_validation_error(exc: ValidationError) -> str:
        return _validation_observation(exc)

    return StructuredTool.from_function(
        coroutine=_ainvoke,
        name=tool_name,
        description=description,
        args_schema=args_schema,
        handle_validation_error=_on_validation_error,
    )


if __name__ == "__main__":
    from schema import GetStatusParams

    # Offline validation smoke (no broker).
    try:
        GetStatusParams.model_validate({})
        raise SystemExit("expected missing order_id failure")
    except ValidationError as e:
        obs = _validation_observation(e)
        assert "INVALID_PARAMS" in obs

    try:
        GetStatusParams.model_validate({"order_id": "ORD-1", "extra": True})
        raise SystemExit("expected extra-field failure")
    except ValidationError as e:
        obs = _validation_observation(e)
        assert "INVALID_PARAMS" in obs

    try:
        GetStatusParams.model_validate({"order_id": 123})
        raise SystemExit("expected wrong-type failure")
    except ValidationError as e:
        obs = _validation_observation(e)
        assert "INVALID_PARAMS" in obs

    ok = GetStatusParams.model_validate({"order_id": "ORD-1001"})
    assert ok.order_id == "ORD-1001"
    print("adapter validation checks ok")
