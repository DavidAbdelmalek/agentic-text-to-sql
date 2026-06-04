"""FastAPI entrypoint (`uvicorn agentic_text_to_sql.api:app`). Phase 5 wires the
/ask endpoint to the agent graph. Health endpoint works now so the container/CI can
probe liveness."""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="agentic-text-to-sql", version="0.1.0")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    sql: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    raise NotImplementedError("Phase 5: invoke the agent graph")
