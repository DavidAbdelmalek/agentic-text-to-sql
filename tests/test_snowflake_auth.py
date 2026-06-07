"""Key-pair auth helper: loading the Snowflake private key from a base64 env var (the path
file-less hosts like Render use). No network, no warehouse."""

from __future__ import annotations

from base64 import b64encode

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_text_to_sql.db import snowflake as sf


def _pem_b64() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return b64encode(pem).decode()


def test_private_key_der_from_b64_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_B64", _pem_b64())
    monkeypatch.setenv("GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE_DEVELOPER", "")
    der = sf._private_key_der()
    assert isinstance(der, bytes) and len(der) > 0


def test_private_key_der_none_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_B64", raising=False)
    assert sf._private_key_der() is None
