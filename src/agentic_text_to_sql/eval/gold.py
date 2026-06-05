"""Load the gold evaluation set (data/eval/gold.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "eval" / "gold.yaml"


@dataclass(frozen=True)
class GoldQuestion:
    id: str
    question: str
    reference_sql: str
    gold_tables: list[str]
    ordered: bool
    smoke: bool


def load_gold(path: Path | None = None, smoke_only: bool = False) -> list[GoldQuestion]:
    doc = yaml.safe_load((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    items = [
        GoldQuestion(
            id=str(q["id"]),
            question=str(q["question"]),
            reference_sql=" ".join(str(q["reference_sql"]).split()),
            gold_tables=list(q.get("gold_tables", [])),
            ordered=bool(q.get("ordered", False)),
            smoke=bool(q.get("smoke", False)),
        )
        for q in doc["questions"]
    ]
    return [q for q in items if q.smoke] if smoke_only else items
