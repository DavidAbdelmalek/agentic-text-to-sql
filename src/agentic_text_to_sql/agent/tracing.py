"""Langfuse tracing. Returns a LangChain/LangGraph callback handler that emits one span per
graph node (inputs/outputs/timings), or None when Langfuse isn't configured — tracing is
strictly optional and never breaks the agent.

Why a callback handler (not manual spans): LangGraph runs each node as a LangChain runnable,
so a single CallbackHandler auto-traces classify/retrieve/generate/guard/execute/repair/
summarize with their state in/out. That's the observability headline — you can see exactly
which node failed, what SQL was generated, and how many repair loops ran, per question.
"""

from __future__ import annotations

from typing import Any

from agentic_text_to_sql.config import Settings


def get_langfuse_handler(settings: Settings) -> Any | None:
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:  # noqa: BLE001 — tracing must never break a query
        return None
