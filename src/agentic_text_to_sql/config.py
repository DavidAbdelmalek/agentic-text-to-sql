"""Central, typed configuration. All env access goes through here — never os.environ
scattered across modules. Loaded from .env (gitignored); see .env.example."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- LLM ---
    # Cortex (in-warehouse) is the only real provider; mock runs the graph offline (CI/tests).
    llm_provider: str = "cortex"  # cortex | mock
    cortex_model: str = "mistral-large2"  # Snowflake Cortex model id

    # --- Langfuse (optional; tracing is a no-op when unset) ---
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None

    # --- Guardrail tunables ---
    sql_max_repair_retries: int = 2
    sql_default_row_limit: int = 1000
    sql_statement_timeout_ms: int = 5000

    # Override the semantic-layer YAML location. Defaults to data/semantic/semantic_layer.yaml
    # (repo layout); set SEMANTIC_LAYER_PATH in the container, where the repo root doesn't exist.
    semantic_layer_path: str | None = None

    @property
    def llm_enabled(self) -> bool:
        """True when the real (Cortex) model can be reached. Eval falls back to mock otherwise."""
        # Cortex runs in-warehouse; reachable when Snowflake creds are present.
        return self.llm_provider == "cortex"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def get_settings() -> Settings:
    """Single entry point. Cheap to call; pydantic-settings re-reads env each time."""
    return Settings()
