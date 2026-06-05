"""Central, typed configuration. All env access goes through here — never os.environ
scattered across modules. Loaded from .env (gitignored); see .env.example."""

from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database: the agent uses ONLY the read-only role DSN ---
    agent_database_url: str = Field(
        default="postgresql://agent_ro:agent_ro_pw@localhost:5432/warehouse",
        description="Read-only role DSN. The only credentials the agent ever touches.",
    )

    # --- LLM ---
    llm_provider: str = "ollama"  # ollama | anthropic | openai | azure | mock
    llm_model: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"
    anthropic_api_key: str | None = None  # reads ANTHROPIC_API_KEY
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None

    # --- Embeddings ---
    embed_provider: str = "local"  # local | openai | azure
    embed_model: str = "BAAI/bge-small-en-v1.5"

    # --- Langfuse (optional; tracing is a no-op when unset) ---
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # --- Guardrail tunables ---
    sql_max_repair_retries: int = 2
    sql_default_row_limit: int = 1000
    sql_statement_timeout_ms: int = 5000

    @property
    def llm_enabled(self) -> bool:
        """True when a real model can be reached. Eval falls back to mock mode otherwise."""
        if self.llm_provider == "mock":
            return False
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "azure":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        return True  # ollama: assume a local server is reachable

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def get_settings() -> Settings:
    """Single entry point. Cheap to call; pydantic-settings re-reads env each time."""
    return Settings()


def superuser_dsn() -> str:
    """BUILD-time superuser DSN (data ingest + semantic-layer build). The AGENT never uses
    this — it only ever connects with the read-only role (Settings.agent_database_url)."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    user = os.environ.get("POSTGRES_SUPERUSER", "postgres")
    pw = os.environ.get("POSTGRES_SUPERUSER_PASSWORD", "postgres")
    db = os.environ.get("POSTGRES_DB", "warehouse")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"
