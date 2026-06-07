"""Parsing the Cortex/AI_COMPLETE response into a bare SQL statement. AI_COMPLETE with
model_parameters returns the completion JSON-encoded (quoted), which the guard would otherwise
reject as a quoted identifier. No network."""

from __future__ import annotations

import json

from agentic_text_to_sql.agent.llm import _extract_sql, _unwrap_completion


def test_unwrap_json_quoted_string() -> None:
    # AI_COMPLETE returns the message as a JSON string -> unwrap the quotes.
    assert _unwrap_completion('" SELECT 1 LIMIT 5"') == " SELECT 1 LIMIT 5"


def test_unwrap_plain_string_passthrough() -> None:
    assert _unwrap_completion("SELECT 1 LIMIT 5") == "SELECT 1 LIMIT 5"


def test_unwrap_choices_object() -> None:
    obj = json.dumps({"choices": [{"messages": "SELECT 2 LIMIT 5"}]})
    assert _unwrap_completion(obj) == "SELECT 2 LIMIT 5"


def test_unwrap_none() -> None:
    assert _unwrap_completion(None) == ""


def test_extract_strips_wrapping_quotes() -> None:
    assert _extract_sql('" SELECT 1 LIMIT 5"') == "SELECT 1 LIMIT 5"


def test_extract_strips_fences_and_semicolon() -> None:
    assert _extract_sql("```sql\nSELECT 1 LIMIT 5;\n```") == "SELECT 1 LIMIT 5"
