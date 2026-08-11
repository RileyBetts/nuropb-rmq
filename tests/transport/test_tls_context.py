"""Unit tests for AmqpConnection TLS profile / SSLContext construction."""

from __future__ import annotations

import ssl
import subprocess
from pathlib import Path

import pytest

from nuropb_rmq.transport.connection import AmqpConnection, ConnectionConfig, TlsProfile


def _openssl_certs(tmp: Path) -> tuple[Path, Path, Path]:
    """Mint a tiny CA + server cert under ``tmp`` via openssl."""
    ca_key, ca_pem = tmp / "ca.key", tmp / "ca.pem"
    srv_key, srv_pem = tmp / "server.key", tmp / "server.pem"
    csr, ext = tmp / "server.csr", tmp / "server.ext"
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
        ["openssl", "genrsa", "-out", str(srv_key), "2048"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "req",
            "-new",
            "-key",
            str(srv_key),
            "-subj",
            "/CN=localhost",
            "-out",
            str(csr),
        ],
        check=True,
        capture_output=True,
    )
    ext.write_text(
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n",
        encoding="utf-8",
    )
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
            str(srv_pem),
            "-days",
            "1",
            "-sha256",
            "-extfile",
            str(ext),
        ],
        check=True,
        capture_output=True,
    )
    return ca_pem, srv_pem, srv_key


def test_verify_full_loads_ca(tmp_path: Path) -> None:
    ca, _srv, _key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            tls_profile=TlsProfile.VERIFY_FULL,
            ca_file=str(ca),
        )
    )
    ctx = conn._build_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_insecure_dev_only_disables_verify() -> None:
    conn = AmqpConnection(
        ConnectionConfig(tls=True, tls_profile=TlsProfile.INSECURE_DEV_ONLY)
    )
    ctx = conn._build_ssl_context()
    assert ctx.verify_mode == ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_custom_san_requires_allowlist(tmp_path: Path) -> None:
    ca, _srv, _key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            tls_profile=TlsProfile.VERIFY_CUSTOM_SAN,
            ca_file=str(ca),
            host="localhost",
            custom_sans=[],
        )
    )
    with pytest.raises(ValueError, match="custom_sans"):
        conn._build_ssl_context()


def test_custom_san_rejects_hostname_not_allowlisted(tmp_path: Path) -> None:
    ca, _srv, _key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            tls_profile=TlsProfile.VERIFY_CUSTOM_SAN,
            ca_file=str(ca),
            host="evil.example",
            custom_sans=["localhost"],
        )
    )
    with pytest.raises(ValueError, match="not in custom_sans"):
        conn._build_ssl_context()


def test_custom_san_ok_when_allowlisted(tmp_path: Path) -> None:
    ca, _srv, _key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            tls_profile=TlsProfile.VERIFY_CUSTOM_SAN,
            ca_file=str(ca),
            host="localhost",
            custom_sans=["localhost"],
        )
    )
    ctx = conn._build_ssl_context()
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_unknown_tls_profile_rejected(tmp_path: Path) -> None:
    ca, _srv, _key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(tls=True, tls_profile="tls-mystery", ca_file=str(ca))
    )
    with pytest.raises(ValueError, match="unknown tls profile"):
        conn._build_ssl_context()


def test_select_sasl_prefers_external_when_cert_configured(tmp_path: Path) -> None:
    ca, srv, key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            ca_file=str(ca),
            cert_file=str(srv),
            key_file=str(key),
        )
    )
    mech, response = conn._select_sasl("PLAIN AMQPLAIN EXTERNAL")
    assert mech == "EXTERNAL"
    assert response == b""


def test_select_sasl_plain_without_client_cert() -> None:
    conn = AmqpConnection(ConnectionConfig(tls=True, username="u", password="p"))
    mech, response = conn._select_sasl("PLAIN EXTERNAL")
    assert mech == "PLAIN"
    assert response == b"\x00u\x00p"


def test_select_sasl_plain_when_external_not_advertised(tmp_path: Path) -> None:
    ca, srv, key = _openssl_certs(tmp_path)
    conn = AmqpConnection(
        ConnectionConfig(
            tls=True,
            ca_file=str(ca),
            cert_file=str(srv),
            key_file=str(key),
            username="u",
            password="p",
        )
    )
    mech, response = conn._select_sasl("PLAIN AMQPLAIN")
    assert mech == "PLAIN"
    assert response == b"\x00u\x00p"


def test_select_sasl_rejects_when_no_supported_mechanism() -> None:
    from nuropb_rmq.protocol.connection_sm import ProtocolError

    conn = AmqpConnection(ConnectionConfig())
    with pytest.raises(ProtocolError, match="no supported SASL"):
        conn._select_sasl("ANONYMOUS")
