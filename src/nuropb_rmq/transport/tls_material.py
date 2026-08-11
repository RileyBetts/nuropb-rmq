"""TLS cert/key material loading: files, in-memory PEM, PKCS#12, secrets hook.

All sources normalize to :class:`TlsMaterial` (PEM) before SSLContext construction.
Private key bytes and PKCS#12 passwords are never included in ``repr``.
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
    """PEM-encoded CA / client cert / key (bytes). PKCS#12 is decoded into these slots."""

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


def _pkcs12_password(password: bytes | str | None) -> bytes | None:
    if password is None:
        return None
    if isinstance(password, str):
        return password.encode("utf-8")
    return password


def _load_pkcs12(data: bytes, password: bytes | str | None) -> TlsMaterial:
    """Decode PKCS#12 into PEM slots. Requires optional ``cryptography`` (``[pkcs12]``)."""
    try:
        from cryptography.hazmat.primitives.serialization import (
            Encoding,
            NoEncryption,
            PrivateFormat,
            pkcs12,
        )
    except ImportError as exc:
        raise ImportError(
            "PKCS#12 support requires cryptography; "
            "install with: pip install 'nuropb-rmq[pkcs12]'"
        ) from exc

    key, cert, additional = pkcs12.load_key_and_certificates(
        data, _pkcs12_password(password)
    )
    if cert is None or key is None:
        raise ValueError("pkcs12: bag must contain a client certificate and private key")

    cert_pem = cert.public_bytes(Encoding.PEM)
    key_pem = key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    ca_parts: list[bytes] = []
    for extra in additional or ():
        if extra is not None:
            ca_parts.append(extra.public_bytes(Encoding.PEM))
    ca_pem = b"".join(ca_parts) if ca_parts else None
    return TlsMaterial(ca_pem=ca_pem, cert_pem=cert_pem, key_pem=key_pem)


def _resolve_pkcs12(config: Any) -> TlsMaterial | None:
    path = getattr(config, "pkcs12_file", None)
    data = getattr(config, "pkcs12_data", None)
    password = getattr(config, "pkcs12_password", None)
    if path is None and data is None:
        return None
    if path is not None and data is not None:
        raise ValueError("pkcs12: provide file path or in-memory data, not both")
    raw = Path(path).read_bytes() if path is not None else data
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        raise ValueError("pkcs12: empty or invalid PKCS#12 data")
    return _load_pkcs12(bytes(raw), password)


def _assert_pkcs12_exclusive(config: Any, from_pkcs12: TlsMaterial, hooked: TlsMaterial) -> None:
    """PKCS#12 conflicts with PEM cert/key (and hook cert/key); CA rules are separate."""
    if hooked.cert_pem is not None or hooked.key_pem is not None:
        raise ValueError(
            "pkcs12: secrets hook already provided cert/key; do not also set PKCS#12"
        )
    for name, path_attr, data_attr in (
        ("cert", "cert_file", "cert_data"),
        ("key", "key_file", "key_data"),
    ):
        if getattr(config, path_attr, None) is not None or getattr(config, data_attr, None) is not None:
            raise ValueError(
                f"pkcs12: conflicts with PEM {name}; use PKCS#12 or PEM cert/key, not both"
            )
    if from_pkcs12.ca_pem is not None:
        if (
            hooked.ca_pem is not None
            or getattr(config, "ca_file", None) is not None
            or getattr(config, "ca_data", None) is not None
        ):
            raise ValueError(
                "pkcs12: bag already includes CA material; "
                "do not also set ca_file / ca_data / secrets ca"
            )


async def resolve_tls_material(config: Any) -> TlsMaterial:
    """Resolve CA/cert/key from PKCS#12, hook, in-memory bytes, or files (each connect)."""
    hooked = TlsMaterial()
    if getattr(config, "tls_secrets", None) is not None:
        hooked = await _invoke_secrets(config.tls_secrets)

    from_pkcs12 = _resolve_pkcs12(config)
    if from_pkcs12 is not None:
        _assert_pkcs12_exclusive(config, from_pkcs12, hooked)
        ca_pem = from_pkcs12.ca_pem
        if ca_pem is None:
            ca_pem = _merge_slot(
                name="ca",
                from_hook=hooked.ca_pem,
                path=getattr(config, "ca_file", None),
                data=getattr(config, "ca_data", None),
            )
        return TlsMaterial(
            ca_pem=ca_pem,
            cert_pem=from_pkcs12.cert_pem,
            key_pem=from_pkcs12.key_pem,
        )

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
