"""FastAPI entrypoint (`uvicorn agentic_text_to_sql.api:app`). Same agent graph as the CLI,
exposed over HTTP. Tracing to Langfuse happens inside run_agent when configured."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from agentic_text_to_sql.agent.graph import run_agent

app = FastAPI(title="agentic-text-to-sql", version="0.1.0")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    question: str
    sql: str | None
    answer: str | None
    failed: bool
    row_count: int


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    state = run_agent(req.question)
    return AskResponse(
        question=req.question,
        sql=state.get("sql"),
        answer=state.get("answer"),
        failed=bool(state.get("failed", False)),
        row_count=len(state.get("result_rows") or []),
    )
