"""Shared graph state passed between LangGraph nodes. Defining it now pins the contract
the Phase-4 nodes implement against."""

from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    retrieved_tables: list[str]  # full schema is always sent; kept for eval retrieval scoring
    sql: str
    result_columns: list[str]
    result_rows: list[tuple[Any, ...]]
    error: str | None
    repair_attempts: int  # bounded by Settings.sql_max_repair_retries
    answer: str
    failed: bool
