"""Phase 1 smoke: the package imports and config loads. Real guardrail/loop/eval tests
arrive with their modules (Phases 4 + 6), authored by the test-author subagent."""

from __future__ import annotations

from agentic_text_to_sql import __version__
from agentic_text_to_sql.config import Settings


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_settings_load_with_safe_defaults() -> None:
    # Ignore any local .env so a stale file can't break the suite. (Env vars still apply, e.g.
    # CI sets LLM_PROVIDER=mock — so accept either valid provider, not just the default.)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_provider in {"cortex", "mock"}
    assert s.sql_max_repair_retries >= 0
    assert s.sql_default_row_limit > 0
