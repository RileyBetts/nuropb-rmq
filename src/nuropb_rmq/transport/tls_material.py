"""TLS cert/key material loading: files, in-memory PEM, secrets-manager hook.

All sources normalize to :class:`TlsMaterial` before SSLContext construction.
Private key bytes are never included in ``repr``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


def _as_pem_bytes(value: bytes | str) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return value


def _redact_pem(label: str, data: bytes | None) -> str:
    if data is None:
        return f"{label}=None"
    return f"{label}=<{len(data)} bytes>"


@dataclass
class TlsMaterial:
    """PEM-encoded CA / client cert / key (bytes). PKCS#12 is out of scope."""

    ca_pem: bytes | None = None
    cert_pem: bytes | None = None
    key_pem: bytes | None = None

    @property
    def has_client_cert(self) -> bool:
        return bool(self.cert_pem)

    def __repr__(self) -> str:
        return (
            "TlsMaterial("
            f"{_redact_pem('ca_pem', self.ca_pem)}, "
            f"{_redact_pem('cert_pem', self.cert_pem)}, "
            f"{_redact_pem('key_pem', self.key_pem)})"
        )


@runtime_checkable
class SecretsProvider(Protocol):
    async def get_tls_material(self) -> TlsMaterial: ...


TlsSecrets = (
    SecretsProvider
    | Callable[[], TlsMaterial]
    | Callable[[], Awaitable[TlsMaterial]]
)


def _slot_from_file_or_data(
    *,
    name: str,
    path: str | None,
    data: bytes | str | None,
) -> bytes | None:
    if path is not None and data is not None:
        raise ValueError(f"{name}: provide file path or in-memory data, not both")
    if data is not None:
        raw = _as_pem_bytes(data)
        if not raw.strip():
            raise ValueError(f"{name}: empty PEM data")
        return raw
    if path is not None:
        raw = Path(path).read_bytes()
        if not raw.strip():
            raise ValueError(f"{name}: empty PEM file {path!r}")
        return raw
    return None


async def _invoke_secrets(provider: TlsSecrets) -> TlsMaterial:
    if isinstance(provider, SecretsProvider) or hasattr(provider, "get_tls_material"):
        result = provider.get_tls_material()  # type: ignore[union-attr]
    else:
        result = provider()  # type: ignore[operator]
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, TlsMaterial):
        raise TypeError("tls_secrets must return TlsMaterial")
    return result


def _merge_slot(
    *,
    name: str,
    from_hook: bytes | None,
    path: str | None,
    data: bytes | str | None,
) -> bytes | None:
    """Precedence: hook value → bytes → file. Conflict if hook set and file/data also set."""
    if from_hook is not None:
        if path is not None or data is not None:
            raise ValueError(
                f"{name}: secrets hook already provided material; "
                "do not also set file path or in-memory data"
            )
        if not from_hook.strip():
            raise ValueError(f"{name}: empty PEM from secrets hook")
        return from_hook
    return _slot_from_file_or_data(name=name, path=path, data=data)


async def resolve_tls_material(config: Any) -> TlsMaterial:
    """Resolve CA/cert/key from hook, in-memory bytes, or files (re-run every connect)."""
    hooked = TlsMaterial()
    if getattr(config, "tls_secrets", None) is not None:
        hooked = await _invoke_secrets(config.tls_secrets)

    return TlsMaterial(
        ca_pem=_merge_slot(
            name="ca",
            from_hook=hooked.ca_pem,
            path=getattr(config, "ca_file", None),
            data=getattr(config, "ca_data", None),
        ),
        cert_pem=_merge_slot(
            name="cert",
            from_hook=hooked.cert_pem,
            path=getattr(config, "cert_file", None),
            data=getattr(config, "cert_data", None),
        ),
        key_pem=_merge_slot(
            name="key",
            from_hook=hooked.key_pem,
            path=getattr(config, "key_file", None),
            data=getattr(config, "key_data", None),
        ),
    )
