"""Phase 6 unit tests for the gold-set loader. No database, no LLM.

Reads the real data/eval/gold.yaml via load_gold() and asserts the contract the
eval harness relies on: enough questions, well-formed items, unique ids, and a
smoke subset that is a strict (non-empty, proper) subset of the full set.
"""

from __future__ import annotations

from agentic_text_to_sql.eval.gold import GoldQuestion, load_gold


def test_load_gold_returns_at_least_15_well_formed_questions() -> None:
    items = load_gold()
    assert len(items) >= 15
    for q in items:
        assert isinstance(q, GoldQuestion)
        assert q.question.strip(), f"{q.id} has empty question"
        assert q.reference_sql.strip(), f"{q.id} has empty reference_sql"
        assert q.gold_tables, f"{q.id} has empty gold_tables"


def test_load_gold_ids_are_unique() -> None:
    ids = [q.id for q in load_gold()]
    assert len(ids) == len(set(ids))


def test_load_gold_smoke_only_is_strict_subset_of_full() -> None:
    full = load_gold()
    smoke = load_gold(smoke_only=True)

    assert smoke, "smoke subset must be non-empty"
    assert all(q.smoke for q in smoke)

    full_ids = {q.id for q in full}
    smoke_ids = {q.id for q in smoke}
    assert smoke_ids < full_ids  # proper subset: subset AND strictly smaller
