"""Unit tests for TLS material resolve (files / bytes / secrets hook)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig
from nuropb_rmq.transport.tls_material import TlsMaterial, resolve_tls_material


def _openssl_certs(tmp: Path) -> tuple[Path, Path, Path]:
    ca_key, ca_pem = tmp / "ca.key", tmp / "ca.pem"
    cli_key, cli_pem = tmp / "client.key", tmp / "client.pem"
    csr, ext = tmp / "client.csr", tmp / "client.ext"
    (tmp / "ca.cnf").write_text(
        "\n".join(
            [
                "[req]",
                "distinguished_name = req_dn",
                "x509_extensions = v3_ca",
                "prompt = no",
                "[req_dn]",
                "CN = test-ca",
                "[v3_ca]",
                "basicConstraints = critical,CA:TRUE",
                "keyUsage = critical,keyCertSign,cRLSign",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["openssl", "genrsa", "-out", str(ca_key), "2048"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-new",
            "-nodes",
            "-key",
            str(ca_key),
            "-sha256",
            "-days",
            "1",
            "-config",
            str(tmp / "ca.cnf"),
            "-out",
            str(ca_pem),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["openssl", "genrsa", "-out", str(cli_key), "2048"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-key",
            str(cli_key),
            "-subj",
            "/CN=client",
            "-out",
            str(csr),
        ],
        check=True,
        capture_output=True,
    )
    ext.write_text("subjectAltName=DNS:client\n", encoding="utf-8")
    subprocess.run(
        [
            "openssl",
            "x509",
            "-req",
            "-in",
            str(csr),
            "-CA",
            str(ca_pem),
            "-CAkey",
            str(ca_key),
            "-CAcreateserial",
            "-out",
            str(cli_pem),
            "-days",
            "1",
            "-sha256",
            "-extfile",
            str(ext),
        ],
        check=True,
        capture_output=True,
    )
    return ca_pem, cli_pem, cli_key


@pytest.mark.asyncio
async def test_resolve_from_files(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    material = await resolve_tls_material(
        ConnectionConfig(ca_file=str(ca), cert_file=str(cert), key_file=str(key))
    )
    assert material.ca_pem == ca.read_bytes()
    assert material.cert_pem == cert.read_bytes()
    assert material.key_pem == key.read_bytes()
    assert material.has_client_cert


@pytest.mark.asyncio
async def test_resolve_from_bytes(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    material = await resolve_tls_material(
        ConnectionConfig(
            ca_data=ca.read_bytes(),
            cert_data=cert.read_text(encoding="utf-8"),
            key_data=key.read_bytes(),
        )
    )
    assert material.ca_pem == ca.read_bytes()
    assert material.cert_pem == cert.read_bytes()
    assert material.key_pem == key.read_bytes()


@pytest.mark.asyncio
async def test_conflict_file_and_bytes(tmp_path: Path) -> None:
    ca, _cert, _key = _openssl_certs(tmp_path)
    with pytest.raises(ValueError, match="ca: provide file path or in-memory data"):
        await resolve_tls_material(
            ConnectionConfig(ca_file=str(ca), ca_data=ca.read_bytes())
        )


@pytest.mark.asyncio
async def test_async_secrets_provider(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    calls = {"n": 0}

    class Provider:
        async def get_tls_material(self) -> TlsMaterial:
            calls["n"] += 1
            return TlsMaterial(
                ca_pem=ca.read_bytes(),
                cert_pem=cert.read_bytes(),
                key_pem=key.read_bytes(),
            )

    cfg = ConnectionConfig(tls_secrets=Provider())
    m1 = await resolve_tls_material(cfg)
    m2 = await resolve_tls_material(cfg)
    assert calls["n"] == 2
    assert m1.has_client_cert and m2.has_client_cert


@pytest.mark.asyncio
async def test_sync_callable_secrets(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    calls = {"n": 0}

    def provider() -> TlsMaterial:
        calls["n"] += 1
        return TlsMaterial(ca_pem=ca.read_bytes(), cert_pem=cert.read_bytes(), key_pem=key.read_bytes())

    material = await resolve_tls_material(ConnectionConfig(tls_secrets=provider))
    assert calls["n"] == 1
    assert material.ca_pem == ca.read_bytes()


@pytest.mark.asyncio
async def test_hook_conflict_with_file(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)

    async def provider() -> TlsMaterial:
        return TlsMaterial(ca_pem=ca.read_bytes())

    with pytest.raises(ValueError, match="ca: secrets hook already provided"):
        await resolve_tls_material(
            ConnectionConfig(tls_secrets=provider, ca_file=str(ca))
        )


@pytest.mark.asyncio
async def test_hook_fills_slot_file_fills_other(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)

    async def provider() -> TlsMaterial:
        return TlsMaterial(ca_pem=ca.read_bytes())

    material = await resolve_tls_material(
        ConnectionConfig(
            tls_secrets=provider,
            cert_file=str(cert),
            key_file=str(key),
        )
    )
    assert material.ca_pem == ca.read_bytes()
    assert material.cert_pem == cert.read_bytes()


@pytest.mark.asyncio
async def test_select_sasl_external_from_secrets_hook(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)

    async def provider() -> TlsMaterial:
        return TlsMaterial(
            ca_pem=ca.read_bytes(),
            cert_pem=cert.read_bytes(),
            key_pem=key.read_bytes(),
        )

    conn = AmqpConnection(ConnectionConfig(tls=True, tls_secrets=provider))
    conn._tls_material = await resolve_tls_material(conn.config)
    mech, response = conn._select_sasl("PLAIN EXTERNAL")
    assert mech == "EXTERNAL"
    assert response == b""


@pytest.mark.asyncio
async def test_connect_invokes_secrets_hook_each_time(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    calls = {"n": 0}

    class Provider:
        async def get_tls_material(self) -> TlsMaterial:
            calls["n"] += 1
            return TlsMaterial(
                ca_pem=ca.read_bytes(),
                cert_pem=cert.read_bytes(),
                key_pem=key.read_bytes(),
            )

    cfg = ConnectionConfig(
        host="127.0.0.1",
        port=1,
        tls=True,
        tls_profile="tls-insecure-dev-only",
        tls_secrets=Provider(),
    )

    async def fake_open(*_a, **_k):  # noqa: ANN002, ANN003
        raise OSError("stop before broker")

    monkeypatch.setattr(
        "nuropb_rmq.transport.connection.asyncio.open_connection",
        fake_open,
    )
    with pytest.raises(OSError, match="stop before broker"):
        await AmqpConnection(cfg).connect()
    with pytest.raises(OSError, match="stop before broker"):
        await AmqpConnection(cfg).connect()
    assert calls["n"] == 2


def test_tls_material_repr_redacts_key(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    material = TlsMaterial(
        ca_pem=ca.read_bytes(),
        cert_pem=cert.read_bytes(),
        key_pem=key.read_bytes(),
    )
    text = repr(material)
    assert "BEGIN PRIVATE KEY" not in text
    assert "BEGIN RSA PRIVATE KEY" not in text
    assert key.read_text(encoding="utf-8").strip() not in text
    assert "key_pem=<" in text


def test_connection_config_repr_redacts_secrets(tmp_path: Path) -> None:
    ca, cert, key = _openssl_certs(tmp_path)
    cfg = ConnectionConfig(
        password="super-secret",
        key_data=key.read_bytes(),
        cert_data=cert.read_bytes(),
        ca_data=ca.read_bytes(),
    )
    text = repr(cfg)
    assert "super-secret" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "BEGIN RSA PRIVATE KEY" not in text
    assert "password=<redacted>" in text
    assert "key_data=<" in text
