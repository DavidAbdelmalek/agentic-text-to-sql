"""FastAPI entrypoint (`uvicorn agentic_text_to_sql.api:app`). Same agent graph as the CLI,
exposed over HTTP. Tracing to Langfuse happens inside run_agent when configured.

/ask is the only expensive route (it drives Cortex + a Snowflake warehouse), so it is guarded:
a static API key (when configured), a per-client rate limit, and a hard request timeout."""

from __future__ import annotations

import asyncio
import secrets

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agentic_text_to_sql.agent.graph import run_agent
from agentic_text_to_sql.config import get_settings

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="agentic-text-to-sql", version="0.1.0")
app.state.limiter = limiter
# slowapi's handler is typed for its own RateLimitExceeded, not Starlette's broad Exception.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]


def _rate_limit() -> str:
    """Per-request limit string, read from settings so it can be tuned via env."""
    return get_settings().api_rate_limit


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Enforce a static API key when one is configured. If api_key is unset (local/dev) the
    endpoint is open; production MUST set API_KEY. Constant-time compare to avoid timing leaks."""
    expected = get_settings().api_key
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or missing API key"
        )


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Bare URL -> interactive API docs."""
    return RedirectResponse(url="/docs")


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
@limiter.limit(_rate_limit)
async def ask(request: Request, req: AskRequest, _: None = Depends(require_api_key)) -> AskResponse:
    # run_agent is blocking (warehouse + Cortex I/O); run it off the event loop with a hard
    # timeout so a slow query can't pin a worker indefinitely.
    timeout_s = get_settings().request_timeout_s
    try:
        state = await asyncio.wait_for(
            asyncio.to_thread(run_agent, req.question), timeout=timeout_s
        )
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="agent timed out"
        ) from None
    return AskResponse(
        question=req.question,
        sql=state.get("sql"),
        answer=state.get("answer"),
        failed=bool(state.get("failed", False)),
        row_count=len(state.get("result_rows") or []),
    )
