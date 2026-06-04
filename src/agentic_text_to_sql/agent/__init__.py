"""The LangGraph agent. Graph: classify -> retrieve schema -> generate SQL ->
guardian validate + EXPLAIN -> execute (read-only) -> bounded reflect/repair ->
summarize. Every node traced in Langfuse. Phase 4 (graph) + Phase 5 (tracing)."""
