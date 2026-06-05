"""Evaluation runner. For each gold question: run the agent, run the reference SQL, and score
execution accuracy (primary), structural similarity (secondary), and retrieval correctness.
Prints a report, writes JSON, and logs scores to Langfuse when configured.

Builds the graph + deps ONCE and reuses them across questions (one embedding-model load, one
set of connections) so the full set runs in seconds, not a rebuild per question.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_text_to_sql.agent.graph import build_default_nodes, build_graph
from agentic_text_to_sql.config import Settings, get_settings
from agentic_text_to_sql.db.read_only_client import ReadOnlyClient
from agentic_text_to_sql.eval.gold import GoldQuestion, load_gold
from agentic_text_to_sql.eval.scoring import (
    execution_accuracy,
    retrieval_metrics,
    structural_similarity,
)

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "eval" / "results"


@dataclass
class QResult:
    id: str
    question: str
    exec_acc: bool
    struct_sim: float
    retrieval_ok: bool
    precision: float
    recall: float
    n_repairs: int
    failed: bool
    agent_sql: str | None
    ref_error: str | None


def _evaluate(gold: list[GoldQuestion], settings: Settings) -> list[QResult]:
    nodes = build_default_nodes(settings)
    app = build_graph(nodes)
    client = ReadOnlyClient(settings.agent_database_url, settings.sql_statement_timeout_ms)

    results: list[QResult] = []
    for q in gold:
        state: dict[str, Any] = app.invoke(
            {"question": q.question, "repair_attempts": 0},
            config={"run_name": f"eval-{q.id}", "metadata": {"eval_id": q.id}},
        )
        try:
            ref_rows = client.execute(q.reference_sql).rows
            ref_error = None
        except Exception as e:  # noqa: BLE001 — record reference failures, don't crash the run
            ref_rows, ref_error = [], str(e).strip()

        exec_acc = ref_error is None and execution_accuracy(
            state.get("result_rows"), ref_rows, ordered=q.ordered
        )
        rscore = retrieval_metrics(state.get("retrieved_tables", []), q.gold_tables)
        results.append(
            QResult(
                id=q.id,
                question=q.question,
                exec_acc=exec_acc,
                struct_sim=structural_similarity(state.get("sql"), q.reference_sql),
                retrieval_ok=rscore.ok,
                precision=rscore.precision,
                recall=rscore.recall,
                n_repairs=state.get("repair_attempts", 0),
                failed=bool(state.get("failed", False)),
                agent_sql=state.get("sql"),
                ref_error=ref_error,
            )
        )
    return results


def _summary(results: list[QResult]) -> dict[str, Any]:
    n = len(results) or 1
    return {
        "n": len(results),
        "execution_accuracy": round(sum(r.exec_acc for r in results) / n, 3),
        "retrieval_ok_rate": round(sum(r.retrieval_ok for r in results) / n, 3),
        "mean_retrieval_recall": round(sum(r.recall for r in results) / n, 3),
        "mean_structural_similarity": round(sum(r.struct_sim for r in results) / n, 3),
    }


def _print_report(results: list[QResult], summary: dict[str, Any], *, mock: bool) -> None:
    mode = "MOCK MODE (validates the harness, not a model)" if mock else "LIVE MODEL"
    print(f"\n=== Eval report — {mode} ===")
    print(f"{'id':<5}{'exec':<6}{'struct':<8}{'retr':<6}{'rep':<5}question")
    print("-" * 72)
    for r in results:
        print(
            f"{r.id:<5}{('PASS' if r.exec_acc else 'FAIL'):<6}"
            f"{r.struct_sim:<8}{('ok' if r.retrieval_ok else 'MISS'):<6}"
            f"{r.n_repairs:<5}{r.question[:38]}"
        )
    print("-" * 72)
    print(
        f"execution_accuracy={summary['execution_accuracy']}  "
        f"retrieval_ok_rate={summary['retrieval_ok_rate']}  "
        f"mean_struct_sim={summary['mean_structural_similarity']}"
    )


def _write_results(payload: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / "latest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _maybe_log_langfuse(results: list[QResult], settings: Settings) -> None:
    """Best-effort: one Langfuse trace per question carrying the three scores. Never fatal."""
    if not settings.langfuse_enabled:
        return
    try:
        from langfuse import Langfuse

        lf = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        for r in results:
            trace = lf.trace(name=f"eval-{r.id}", input=r.question, output=r.agent_sql)
            trace.score(name="execution_accuracy", value=1.0 if r.exec_acc else 0.0)
            trace.score(name="retrieval_recall", value=r.recall)
            trace.score(name="structural_similarity", value=r.struct_sim)
        lf.flush()
    except Exception:  # noqa: BLE001
        pass


def run_eval(smoke: bool = False, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    gold = load_gold(smoke_only=smoke)
    results = _evaluate(gold, settings)
    summary = _summary(results)

    _print_report(results, summary, mock=not settings.llm_enabled)
    payload = {
        "smoke": smoke,
        "mock": not settings.llm_enabled,
        "summary": summary,
        "results": [asdict(r) for r in results],
    }
    path = _write_results(payload)
    _maybe_log_langfuse(results, settings)
    print(f"results -> {path}")
    return payload
