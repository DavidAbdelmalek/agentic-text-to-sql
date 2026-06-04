"""Shared graph state passed between LangGraph nodes. Defining it now pins the contract
the Phase-4 nodes implement against."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    question_class: str  # e.g. aggregate | lookup | trend | ambiguous
    retrieved_tables: list[str]
    schema_context: str
    sql: str
    params: dict[str, Any]
    guard_reasons: list[str]
    result_columns: list[str]
    result_rows: list[tuple[Any, ...]]
    error: str | None
    repair_attempts: int  # bounded by Settings.sql_max_repair_retries
    answer: str
    failed: bool
