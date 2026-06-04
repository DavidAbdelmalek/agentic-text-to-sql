"""CLI entrypoint (`ttsql ask "<question>"`). Runs the LangGraph agent end to end."""

from __future__ import annotations

import typer

app = typer.Typer(help="Ask business questions over the warehouse in natural language.")


@app.callback()
def main() -> None:
    """Agentic text-to-SQL. Use the `ask` command."""


@app.command()
def ask(question: str, show_rows: int = 10) -> None:
    """Answer a natural-language question by generating + running read-only SQL."""
    from agentic_text_to_sql.agent.graph import run_agent

    state = run_agent(question)

    typer.secho("\nSQL", fg=typer.colors.CYAN, bold=True)
    typer.echo(state.get("sql", "<none>"))

    if state.get("failed"):
        typer.secho("\nFAILED", fg=typer.colors.RED, bold=True)
        typer.echo(state.get("answer"))
        raise typer.Exit(code=1)

    columns = state.get("result_columns") or []
    rows = state.get("result_rows") or []
    if columns:
        typer.secho("\nRESULT", fg=typer.colors.GREEN, bold=True)
        typer.echo(" | ".join(columns))
        for row in rows[:show_rows]:
            typer.echo(" | ".join(str(v) for v in row))
        if len(rows) > show_rows:
            typer.echo(f"... ({len(rows)} rows total)")

    typer.secho("\nANSWER", fg=typer.colors.GREEN, bold=True)
    typer.echo(state.get("answer"))


if __name__ == "__main__":
    app()
