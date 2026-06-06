"""Central, typed configuration. All env access goes through here — never os.environ
scattered across modules. Loaded from .env (gitignored); see .env.example."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    llm_provider: str = "cortex"  # cortex | anthropic | openai | azure | mock
    cortex_model: str = "mistral-large2"  # used by cortex provider
    llm_model: str = "gpt-4o-mini"  # model id for anthropic | openai (azure uses deployment)
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_deployment: str | None = None

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
        if self.llm_provider == "cortex":
            return True  # runs in-warehouse; reachable when Snowflake creds are present
        if self.llm_provider == "anthropic":
            return bool(self.anthropic_api_key)
        if self.llm_provider == "openai":
            return bool(self.openai_api_key)
        if self.llm_provider == "azure":
            return bool(self.azure_openai_api_key and self.azure_openai_endpoint)
        return False  # unknown provider

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def get_settings() -> Settings:
    """Single entry point. Cheap to call; pydantic-settings re-reads env each time."""
    return Settings()
