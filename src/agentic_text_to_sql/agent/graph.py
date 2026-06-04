"""LangGraph wiring for the text-to-SQL agent.

    classify -> retrieve -> generate -> guard --(ok)--> execute --(ok)--> summarize -> END
                                ^          |                  |
                                |        (error)            (error)
                                |          v                  v
                                +------- repair <-------------+
                                           |
                                  (budget spent) -> give_up -> END

Why a graph and not one prompt (interview): the guard sits BETWEEN generation and execution
as its own node, and the repair loop is an explicit, bounded cycle in the edges — neither is
expressible inside a single LLM call. The state is typed and every transition is inspectable,
which is also what makes per-node tracing (Phase 5) and evaluation (Phase 6) possible.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from agentic_text_to_sql.agent.llm import get_llm
from agentic_text_to_sql.agent.nodes import AgentNodes
from agentic_text_to_sql.agent.state import AgentState
from agentic_text_to_sql.config import Settings, get_settings
from agentic_text_to_sql.db.read_only_client import ReadOnlyClient
from agentic_text_to_sql.semantic_layer.loader import SemanticLayer, load_semantic_layer
from agentic_text_to_sql.semantic_layer.retriever import get_retriever


def build_graph(nodes: AgentNodes) -> Any:
    """Compile the agent graph from an AgentNodes (deps already wired). Separated from
    dependency construction so tests can inject fakes."""
    g = StateGraph(AgentState)
    g.add_node("classify", nodes.classify)
    g.add_node("retrieve", nodes.retrieve)
    g.add_node("generate", nodes.generate)
    g.add_node("guard", nodes.guard)
    g.add_node("execute", nodes.execute)
    g.add_node("repair", nodes.repair)
    g.add_node("summarize", nodes.summarize)
    g.add_node("give_up", nodes.give_up)

    g.add_edge(START, "classify")
    g.add_edge("classify", "retrieve")
    g.add_edge("retrieve", "generate")
    g.add_edge("generate", "guard")
    g.add_conditional_edges(
        "guard", nodes.route_after_guard, {"repair": "repair", "execute": "execute"}
    )
    g.add_conditional_edges(
        "execute", nodes.route_after_execute, {"repair": "repair", "summarize": "summarize"}
    )
    g.add_conditional_edges(
        "repair", nodes.route_after_repair, {"generate": "generate", "give_up": "give_up"}
    )
    g.add_edge("summarize", END)
    g.add_edge("give_up", END)
    return g.compile()


def build_default_nodes(settings: Settings | None = None) -> AgentNodes:
    settings = settings or get_settings()
    layer: SemanticLayer = load_semantic_layer()
    return AgentNodes(
        settings=settings,
        llm=get_llm(settings),
        retriever=get_retriever(settings, layer),
        client=ReadOnlyClient(settings.agent_database_url, settings.sql_statement_timeout_ms),
        layer=layer,
    )


def run_agent(question: str, settings: Settings | None = None) -> AgentState:
    """Convenience entry point: build the default graph and answer one question."""
    app = build_graph(build_default_nodes(settings))
    final: AgentState = app.invoke({"question": question, "repair_attempts": 0})
    return final


if __name__ == "__main__":
    import sys

    out = run_agent(" ".join(sys.argv[1:]) or "Total revenue by country")
    print("\nSQL:\n", out.get("sql"))
    print("\nANSWER:\n", out.get("answer"))
