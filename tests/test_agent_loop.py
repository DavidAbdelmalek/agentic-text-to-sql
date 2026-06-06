"""Phase 4 unit tests for the agent graph's bounded reflect/repair loop. No database.

Everything the graph touches is a minimal fake (LLM, retriever, DB client), so these run on
the CI fast path. The headline assertion is that the repair loop is BOUNDED: a perpetually
failing guard must give up cleanly after `sql_max_repair_retries + 1` generations rather than
spinning forever. The routers are also unit-tested directly.
"""

from __future__ import annotations

from agentic_text_to_sql.agent.graph import build_graph
from agentic_text_to_sql.agent.nodes import AgentNodes, render_schema
from agentic_text_to_sql.config import Settings
from agentic_text_to_sql.db.read_only_client import QueryResult
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer


# --------------------------------------------------------------------------- fakes
class FakeLLM:
    """Records how many times generate_sql is called; returns a fixed SQL string."""

    def __init__(self, sql: str) -> None:
        self._sql = sql
        self.generate_calls = 0
        self.summarize_calls = 0

    def classify(self, question: str) -> str:
        return "aggregate"

    def generate_sql(self, question: str, schema_context: str, error: str | None) -> str:
        self.generate_calls += 1
        return self._sql

    def summarize(self, question: str, result_preview: str) -> str:
        self.summarize_calls += 1
        return f"answer: {result_preview}"


class FakeClient:
    """Stand-in for ReadOnlyClient. explain() returns plan text (no error -> guard passes);
    execute() returns a fixed QueryResult. Neither touches a database."""

    def __init__(self, result: QueryResult | None = None) -> None:
        self._result = result or QueryResult(columns=[], rows=[])
        self.explain_calls = 0
        self.execute_calls = 0

    def explain(self, sql: str, params: dict | None = None) -> str:
        self.explain_calls += 1
        return ""

    def execute(self, sql: str, params: dict | None = None) -> QueryResult:
        self.execute_calls += 1
        return self._result


def _nodes(llm: FakeLLM, client: FakeClient, layer: SemanticLayer, retries: int = 2) -> AgentNodes:
    settings = Settings(sql_max_repair_retries=retries, sql_default_row_limit=1000)
    all_tables = [t.name for t in layer.tables]
    return AgentNodes(
        settings=settings,
        llm=llm,
        client=client,
        layer=layer,
        schema_context=render_schema(layer, all_tables),
        all_table_names=all_tables,
    )


# --------------------------------------------------------------------------- loop is bounded
def test_repair_loop_is_bounded_and_gives_up(tiny_layer: SemanticLayer) -> None:
    """The guard REJECTs every generated query (hallucinated column), so the loop can never
    succeed. It must still terminate: give_up after sql_max_repair_retries + 1 generations."""
    retries = 2
    llm = FakeLLM("SELECT bogus_col FROM fct_sales LIMIT 10")
    client = FakeClient()
    graph = build_graph(_nodes(llm, client, tiny_layer, retries=retries))

    final = graph.invoke({"question": "q", "repair_attempts": 0})

    assert final.get("failed") is True
    # The loop is bounded: repair_attempts settles at retries + 1, not unbounded.
    assert final["repair_attempts"] == retries + 1
    # And the LLM was asked to generate exactly retries + 1 times.
    assert llm.generate_calls == retries + 1
    # A rejected query never reaches the DB layer.
    assert client.execute_calls == 0


# --------------------------------------------------------------------------- happy path
def test_success_path_produces_answer(tiny_layer: SemanticLayer) -> None:
    rows = [("UK", 100), ("US", 50)]
    result = QueryResult(columns=["country", "revenue_gbp"], rows=rows)
    llm = FakeLLM(
        "SELECT c.country, SUM(f.revenue_gbp) AS revenue_gbp "
        "FROM fct_sales f JOIN dim_country c ON f.country_key = c.country_key "
        "GROUP BY c.country LIMIT 100"
    )
    client = FakeClient(result=result)
    graph = build_graph(_nodes(llm, client, tiny_layer))

    final = graph.invoke({"question": "revenue by country", "repair_attempts": 0})

    assert "answer" in final and final["answer"]
    assert not final.get("failed")
    assert final["result_rows"] == rows
    assert client.execute_calls == 1
    assert llm.generate_calls == 1


# --------------------------------------------------------------------------- routers
def test_route_after_guard(tiny_layer: SemanticLayer) -> None:
    nodes = _nodes(FakeLLM("x"), FakeClient(), tiny_layer)
    assert nodes.route_after_guard({"error": "boom"}) == "repair"
    assert nodes.route_after_guard({"error": None}) == "execute"
    assert nodes.route_after_guard({}) == "execute"


def test_route_after_repair_is_bounded(tiny_layer: SemanticLayer) -> None:
    nodes = _nodes(FakeLLM("x"), FakeClient(), tiny_layer, retries=2)
    # Within budget -> keep repairing.
    assert nodes.route_after_repair({"repair_attempts": 1}) == "generate"
    assert nodes.route_after_repair({"repair_attempts": 2}) == "generate"
    # Budget spent (attempts exceeds max) -> give up.
    assert nodes.route_after_repair({"repair_attempts": 3}) == "give_up"
