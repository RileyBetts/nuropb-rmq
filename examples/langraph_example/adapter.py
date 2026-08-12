# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""Thin LangGraph adapter: remote_node over nuropb-rmq RpcClient."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from nuropb_rmq import DEFAULT_MESH_EXCHANGE, RpcClient, RpcError
from nuropb_rmq.patterns.errors import CONNECTION_LOST


class RemoteNodeError(Exception):
    """Terminal remote-node failure (not retriable by LangGraph checkpoint replay)."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class RetriableRemoteError(Exception):
    """Client connection lost; after rebind, LangGraph may replay the node."""

    def __init__(self, message: str, *, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause


def _ensure_json_serializable(label: str, value: Any) -> None:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise RemoteNodeError(
            f"{label} is not JSON-serializable: {value!r}"
        ) from exc


def _slice_params(state: dict[str, Any], reads: Sequence[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key in reads:
        if key not in state:
            raise RemoteNodeError(f"missing read key in state: {key!r}")
        value = state[key]
        _ensure_json_serializable(f"params[{key!r}]", value)
        params[key] = value
    return params


def _slice_result(result: Any, writes: Sequence[str]) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RemoteNodeError(f"remote result must be an object, got {type(result).__name__}")
    allowed = set(writes)
    extra = set(result) - allowed
    if extra:
        raise RemoteNodeError(f"remote result has undeclared write keys: {sorted(extra)}")
    out: dict[str, Any] = {}
    for key in writes:
        if key not in result:
            raise RemoteNodeError(f"remote result missing write key: {key!r}")
        value = result[key]
        _ensure_json_serializable(f"result[{key!r}]", value)
        out[key] = value
    return out


def _is_connection_lost(err: RpcError) -> bool:
    if err.code == CONNECTION_LOST:
        return True
    data = err.data
    if isinstance(data, dict) and data.get("code_name") == "CONNECTION_LOST":
        return True
    return False


def remote_node(
    client: RpcClient,
    *,
    service: str,
    method: str,
    reads: Sequence[str],
    writes: Sequence[str],
    exchange: str = DEFAULT_MESH_EXCHANGE,
    on_connection_lost: Callable[[], Awaitable[None]] | None = None,
) -> Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]:
    """Return an async LangGraph node that runs ``service.method`` over the mesh.

    Declared ``reads`` are serialized into JSON-RPC params; only ``writes`` are
    accepted back and merged. Reject-not-coerce at both boundaries.
    """
    if not reads:
        raise ValueError("reads must be non-empty")
    if not writes:
        raise ValueError("writes must be non-empty")
    rk = f"{service}.{method}" if not method.startswith(f"{service}.") else method

    async def _node(state: dict[str, Any]) -> dict[str, Any]:
        params = _slice_params(state, reads)
        try:
            result = await client.request(rk, rk, params, exchange=exchange)
        except RpcError as err:
            if _is_connection_lost(err):
                if on_connection_lost is not None:
                    await on_connection_lost()
                raise RetriableRemoteError(
                    f"connection lost during remote node {rk}; rebound for replay",
                    cause=err,
                ) from err
            raise RemoteNodeError(
                f"remote node {rk} failed: {err}",
                cause=err,
            ) from err
        return _slice_result(result, writes)

    return _node


if __name__ == "__main__":
    # Slice validation smoke (no broker).
    bad_state = {"document_id": "x"}
    try:
        _slice_params(bad_state, ["document_id", "raw_text"])
        raise SystemExit("expected missing-key failure")
    except RemoteNodeError as e:
        assert "raw_text" in str(e)

    try:
        _slice_result({"vendor": "A", "extra": 1}, ["vendor"])
        raise SystemExit("expected undeclared-key failure")
    except RemoteNodeError as e:
        assert "extra" in str(e)

    ok = _slice_result({"vendor": "A", "total": 1.0}, ["vendor", "total"])
    assert ok == {"vendor": "A", "total": 1.0}
    print("adapter slice checks ok")
