"""Visualize the agent graph structure."""

from agentic_text_to_sql.agent.graph import build_default_nodes, build_graph

nodes = build_default_nodes()
graph = build_graph(nodes)

print(graph.get_graph().draw_mermaid())
