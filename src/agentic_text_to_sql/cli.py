"""CLI entrypoint (`ttsql ...`). Phase 5 wires this to the agent graph."""

from __future__ import annotations

import typer

app = typer.Typer(help="Ask business questions over the warehouse in natural language.")


@app.command()
def ask(question: str) -> None:
    """Answer a natural-language question by generating + running read-only SQL."""
    raise NotImplementedError("Phase 5: run the agent graph and print the answer")


if __name__ == "__main__":
    app()
