# Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
# Released under Apache 2.0 license as described in the file LICENSE.

"""JSON-RPC error taxonomy and allowlisted error.data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Architecture bands (-33000..-33999)
INVALID_ID = -33001
ID_COLLISION = -33002
INVALID_ENVELOPE = -33003
UNAUTHORIZED = -33100
CLAIMS_MISSING = -33101
CLAIMS_EXPIRED = -33102
CLAIMS_UNBOUND = -33103
BIND_REFUSED = -33201
REQUEST_TIMEOUT = -33300
CONNECTION_LOST = -33400
CONNECTION_BLOCKED = -33401
PUBLISH_NACK = -33402
SERVER_ERROR = -32000  # shared coarse fallback only

CODE_NAMES: dict[int, str] = {
    INVALID_ID: "INVALID_ID",
    ID_COLLISION: "ID_COLLISION",
    INVALID_ENVELOPE: "INVALID_ENVELOPE",
    UNAUTHORIZED: "UNAUTHORIZED",
    CLAIMS_MISSING: "CLAIMS_MISSING",
    CLAIMS_EXPIRED: "CLAIMS_EXPIRED",
    CLAIMS_UNBOUND: "CLAIMS_UNBOUND",
    BIND_REFUSED: "BIND_REFUSED",
    REQUEST_TIMEOUT: "REQUEST_TIMEOUT",
    CONNECTION_LOST: "CONNECTION_LOST",
    CONNECTION_BLOCKED: "CONNECTION_BLOCKED",
    PUBLISH_NACK: "PUBLISH_NACK",
    SERVER_ERROR: "SERVER_ERROR",
}

_ALLOWED_DATA_KEYS = frozenset({"code_name", "retryable", "correlation_id", "method"})


@dataclass
class RpcError(Exception):
    code: int
    message: str
    data: dict[str, Any] | None = None
    id: str | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


def make_error_data(
    *,
    code: int,
    retryable: bool = False,
    correlation_id: str | None = None,
    method: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "code_name": CODE_NAMES.get(code, "UNKNOWN"),
        "retryable": retryable,
    }
    if correlation_id is not None:
        data["correlation_id"] = correlation_id
    if method is not None:
        data["method"] = method
    return allowlist_error_data(data)


def allowlist_error_data(data: dict[str, Any] | None) -> dict[str, Any] | None:
    if data is None:
        return None
    return {k: v for k, v in data.items() if k in _ALLOWED_DATA_KEYS}
