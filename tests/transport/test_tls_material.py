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
        pkcs12_password="p12-secret",
    )
    text = repr(cfg)
    assert "super-secret" not in text
    assert "p12-secret" not in text
    assert "BEGIN PRIVATE KEY" not in text
    assert "BEGIN RSA PRIVATE KEY" not in text
    assert "password=<redacted>" in text
    assert "pkcs12_password=<redacted>" in text
    assert "key_data=<" in text


def _require_cryptography() -> None:
    pytest.importorskip("cryptography")


def _make_pkcs12(tmp: Path, *, password: bytes | None, include_ca: bool) -> bytes:
    _require_cryptography()
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-ca")])
    now = datetime.datetime.now(datetime.UTC)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    cli_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cli_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "client")])
    cli_cert = (
        x509.CertificateBuilder()
        .subject_name(cli_name)
        .issuer_name(ca_name)
        .public_key(cli_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(ca_key, hashes.SHA256())
    )
    encryption = (
        serialization.BestAvailableEncryption(password)
        if password is not None
        else serialization.NoEncryption()
    )
    return pkcs12.serialize_key_and_certificates(
        name=b"client",
        key=cli_key,
        cert=cli_cert,
        cas=[ca_cert] if include_ca else None,
        encryption_algorithm=encryption,
    )


@pytest.mark.asyncio
async def test_resolve_from_pkcs12_file(tmp_path: Path) -> None:
    p12 = _make_pkcs12(tmp_path, password=b"secret", include_ca=True)
    path = tmp_path / "client.p12"
    path.write_bytes(p12)
    material = await resolve_tls_material(
        ConnectionConfig(pkcs12_file=str(path), pkcs12_password="secret")
    )
    assert material.has_client_cert
    assert material.cert_pem and b"BEGIN CERTIFICATE" in material.cert_pem
    assert material.key_pem and b"BEGIN PRIVATE KEY" in material.key_pem
    assert material.ca_pem and b"BEGIN CERTIFICATE" in material.ca_pem


@pytest.mark.asyncio
async def test_resolve_from_pkcs12_data_without_ca_uses_ca_file(tmp_path: Path) -> None:
    ca, _cert, _key = _openssl_certs(tmp_path)
    p12 = _make_pkcs12(tmp_path, password=None, include_ca=False)
    material = await resolve_tls_material(
        ConnectionConfig(pkcs12_data=p12, ca_file=str(ca))
    )
    assert material.has_client_cert
    assert material.ca_pem == ca.read_bytes()


@pytest.mark.asyncio
async def test_pkcs12_conflicts_with_pem_cert(tmp_path: Path) -> None:
    _ca, cert, _key = _openssl_certs(tmp_path)
    p12 = _make_pkcs12(tmp_path, password=None, include_ca=False)
    with pytest.raises(ValueError, match="pkcs12: conflicts with PEM cert"):
        await resolve_tls_material(
            ConnectionConfig(pkcs12_data=p12, cert_file=str(cert))
        )


@pytest.mark.asyncio
async def test_pkcs12_file_and_data_conflict(tmp_path: Path) -> None:
    p12 = _make_pkcs12(tmp_path, password=None, include_ca=False)
    path = tmp_path / "client.p12"
    path.write_bytes(p12)
    with pytest.raises(ValueError, match="pkcs12: provide file path or in-memory data"):
        await resolve_tls_material(ConnectionConfig(pkcs12_file=str(path), pkcs12_data=p12))


@pytest.mark.asyncio
async def test_pkcs12_ca_bag_conflicts_with_ca_file(tmp_path: Path) -> None:
    ca, _cert, _key = _openssl_certs(tmp_path)
    p12 = _make_pkcs12(tmp_path, password=None, include_ca=True)
    with pytest.raises(ValueError, match="pkcs12: bag already includes CA"):
        await resolve_tls_material(ConnectionConfig(pkcs12_data=p12, ca_file=str(ca)))


@pytest.mark.asyncio
async def test_pkcs12_conflicts_with_secrets_cert(tmp_path: Path) -> None:
    _ca, cert, key = _openssl_certs(tmp_path)
    p12 = _make_pkcs12(tmp_path, password=None, include_ca=False)

    async def provider() -> TlsMaterial:
        return TlsMaterial(cert_pem=cert.read_bytes(), key_pem=key.read_bytes())

    with pytest.raises(ValueError, match="pkcs12: secrets hook already provided"):
        await resolve_tls_material(ConnectionConfig(pkcs12_data=p12, tls_secrets=provider))


@pytest.mark.asyncio
async def test_select_sasl_external_from_pkcs12(tmp_path: Path) -> None:
    p12 = _make_pkcs12(tmp_path, password=b"x", include_ca=True)
    cfg = ConnectionConfig(tls=True, pkcs12_data=p12, pkcs12_password=b"x")
    conn = AmqpConnection(cfg)
    conn._tls_material = await resolve_tls_material(cfg)
    mech, response = conn._select_sasl("PLAIN EXTERNAL")
    assert mech == "EXTERNAL"
    assert response == b""
