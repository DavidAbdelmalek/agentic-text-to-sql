"""Snowflake connection helper (key-pair auth).

Reads the existing ``GENAI_DBT_SNOWFLAKE_*`` environment variables rather than copying secrets
into .env. Two roles:
- BUILD role (env default, e.g. ACCOUNTADMIN) — ingest, dbt, and one-time provisioning.
- AGENT role (read-only, e.g. AGENT_RO) — the only role the agent's queries ever use.

The read-only guarantee is enforced by connecting the agent session with a role that holds
only SELECT (+ Cortex usage) — Snowflake rejects writes at the engine level, exactly like the
Postgres read-only role did.
"""

from __future__ import annotations

import os
from typing import Any

# Vendor env var names (already set in the developer's environment).
_E_ACCOUNT = "GENAI_DBT_SNOWFLAKE_ACCOUNT"
_E_USER = "GENAI_DBT_SNOWFLAKE_USER_DEVELOPER"
_E_ROLE = "GENAI_DBT_SNOWFLAKE_ROLE_DEVELOPER"
_E_WAREHOUSE = "GENAI_DBT_SNOWFLAKE_WAREHOUSE_DEVELOPER"
_E_DATABASE = "GENAI_DBT_SNOWFLAKE_DATABASE_DEVELOPER"
_E_SCHEMA = "GENAI_DBT_SNOWFLAKE_SCHEMA_DEVELOPER"
_E_PK_PATH = "GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_PATH_DEVELOPER"
_E_PK_PWD = "GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_PASSPHRASE_DEVELOPER"
# Base64 of the PEM private key. Used on hosts that only provide env vars, not files
# (Render, Cloud Run, HF Spaces). Takes precedence over the key-file path when set.
_E_PK_B64 = "GENAI_DBT_SNOWFLAKE_PRIVATE_KEY_B64"

# Project layout inside the existing GENAI_DEV database. raw load and curated marts live in
# separate schemas so the read-only agent role can be granted the marts schema only.
RAW_SCHEMA = "TTSQL_RAW"
MARTS_SCHEMA = "TTSQL"
AGENT_ROLE = "AGENT_RO"


def account() -> str:
    return os.environ[_E_ACCOUNT]


def build_role() -> str:
    return os.environ.get(_E_ROLE, "ACCOUNTADMIN")


def database() -> str:
    return os.environ[_E_DATABASE]


def _private_key_pwd() -> bytes | None:
    # Strip wrapping quotes/whitespace — an empty/`""` passphrase means the key is unencrypted.
    pwd = (os.environ.get(_E_PK_PWD) or "").strip().strip('"').strip("'")
    return pwd.encode() if pwd else None


def _private_key_der() -> bytes | None:
    """When the key is supplied as base64 PEM via env (no file on disk), decode it and return
    DER bytes for the connector's ``private_key`` arg. Returns None to fall back to the file."""
    b64 = (os.environ.get(_E_PK_B64) or "").strip()
    if not b64:
        return None
    from base64 import b64decode

    from cryptography.hazmat.primitives import serialization

    key = serialization.load_pem_private_key(b64decode(b64), password=_private_key_pwd())
    return key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def connect(
    *,
    role: str | None = None,
    database_: str | None = None,
    schema: str | None = None,
) -> Any:
    """Open a Snowflake connection. Defaults to the build role; pass role=AGENT_RO for the
    read-only agent session."""
    import snowflake.connector as sf

    # Prefer an in-env base64 key (file-less hosts); otherwise read the key file from disk.
    der = _private_key_der()
    key_kwargs: dict[str, Any] = (
        {"private_key": der}
        if der is not None
        else {
            "private_key_file": os.environ[_E_PK_PATH],
            "private_key_file_pwd": _private_key_pwd(),
        }
    )

    return sf.connect(
        account=os.environ[_E_ACCOUNT],
        user=os.environ[_E_USER],
        role=role or build_role(),
        warehouse=os.environ[_E_WAREHOUSE],
        database=database_ or os.environ[_E_DATABASE],
        schema=schema or os.environ[_E_SCHEMA],
        client_session_keep_alive=False,
        **key_kwargs,
    )
