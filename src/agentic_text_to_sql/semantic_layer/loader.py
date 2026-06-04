"""Load + represent the semantic layer (data/semantic/semantic_layer.yaml).

This is the agent's single source of truth for what tables/columns exist. The retriever
embeds it, the SQL generator is grounded in it, and the guardrail rejects any identifier not
in `allowed_identifiers()` — that last check is the anti-hallucination backstop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "semantic" / "semantic_layer.yaml"


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    description: str = ""
    is_pk: bool = False
    is_fk: bool = False
    is_measure: bool = False
    is_dimension: bool = False


@dataclass(frozen=True)
class ForeignKey:
    column: str
    references: str  # "table.column"


@dataclass(frozen=True)
class Table:
    name: str
    grain: str
    description: str
    columns: list[Column]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)

    def document(self) -> str:
        """The text we embed / keyword-index for retrieval: name, grain, description, and
        every column name + description. Rich enough to match a natural-language question."""
        cols = "; ".join(f"{c.name} ({c.description})" for c in self.columns)
        return f"{self.name}: {self.description} grain: {self.grain}. columns: {cols}"


@dataclass(frozen=True)
class SemanticLayer:
    tables: list[Table]
    joinable_paths: list[str] = field(default_factory=list)

    def get(self, name: str) -> Table | None:
        return next((t for t in self.tables if t.name == name), None)

    def allowed_identifiers(self) -> set[str]:
        """Every legal identifier: table names, bare column names, and table.column. The
        guardrail resolves generated SQL identifiers against this set."""
        ids: set[str] = set()
        for t in self.tables:
            ids.add(t.name)
            for c in t.columns:
                ids.add(c.name)
                ids.add(f"{t.name}.{c.name}")
        return ids


def _to_column(raw: dict[str, Any]) -> Column:
    return Column(
        name=str(raw["name"]),
        type=str(raw.get("type", "")),
        description=str(raw.get("description", "")),
        is_pk=bool(raw.get("is_pk", False)),
        is_fk=bool(raw.get("is_fk", False)),
        is_measure=bool(raw.get("is_measure", False)),
        is_dimension=bool(raw.get("is_dimension", False)),
    )


def _to_table(raw: dict[str, Any]) -> Table:
    fks = [
        ForeignKey(column=str(fk["column"]), references=str(fk["references"]))
        for fk in (raw.get("foreign_keys") or [])
    ]
    return Table(
        name=str(raw["name"]),
        grain=str(raw.get("grain", "")),
        description=str(raw.get("description", "")),
        columns=[_to_column(c) for c in raw["columns"]],
        primary_key=[str(x) for x in (raw.get("primary_key") or [])],
        foreign_keys=fks,
    )


def load_semantic_layer(path: Path | None = None) -> SemanticLayer:
    doc = yaml.safe_load((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    tables = [_to_table(t) for t in doc["tables"]]
    return SemanticLayer(tables=tables, joinable_paths=list(doc.get("joinable_paths", [])))
