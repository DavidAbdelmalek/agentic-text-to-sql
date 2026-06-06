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

# Project layout inside the existing GENAI_DEV database. raw load and curated marts live in
# separate schemas so the read-only agent role can be granted the marts schema only.
RAW_SCHEMA = "TTSQL_RAW"
MARTS_SCHEMA = "TTSQL"
AGENT_ROLE = "AGENT_RO"
# Cortex LLM available in eu-central-1 (Claude needs cross-region; llama/mistral are local).
DEFAULT_CORTEX_MODEL = "llama3.1-70b"


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


def connect(
    *,
    role: str | None = None,
    database_: str | None = None,
    schema: str | None = None,
) -> Any:
    """Open a Snowflake connection. Defaults to the build role; pass role=AGENT_RO for the
    read-only agent session."""
    import snowflake.connector as sf

    return sf.connect(
        account=os.environ[_E_ACCOUNT],
        user=os.environ[_E_USER],
        private_key_file=os.environ[_E_PK_PATH],
        private_key_file_pwd=_private_key_pwd(),
        role=role or build_role(),
        warehouse=os.environ[_E_WAREHOUSE],
        database=database_ or os.environ[_E_DATABASE],
        schema=schema or os.environ[_E_SCHEMA],
        client_session_keep_alive=False,
    )
