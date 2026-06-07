# syntax=docker/dockerfile:1
#
# Multi-stage build for the agentic text-to-SQL API.
# Only the agent orchestration (LangGraph, FastAPI, the SQL guard) is containerised. The LLM is
# Snowflake Cortex and runs IN the warehouse, so no model weights ship in the image, and the
# agent reaches Snowflake at runtime via the GENAI_DBT_SNOWFLAKE_* env vars (mounted, never baked).

# ---- builder: resolve + install the locked deps into a venv -----------------------------------
FROM python:3.11-slim AS builder

# uv from its official image (pinned). Builds are reproducible from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install runtime deps first (no dev group, no project) so this layer is cached unless the
# lockfile changes — source edits don't bust the dependency layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Add the source and install the project itself into the same venv.
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# ---- runtime: slim image, non-root, production ASGI server ------------------------------------
FROM python:3.11-slim AS runtime

# Unprivileged user: the agent only ever reads, and nothing in the container needs root.
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app
# The generated semantic layer is the agent's grounding + the guard's allowed-identifier set.
# It lives at the repo root in dev; ship it explicitly and point the loader at it via env.
COPY --chown=appuser:appuser data/semantic/semantic_layer.yaml /app/semantic_layer.yaml

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    LLM_PROVIDER=cortex \
    SEMANTIC_LAYER_PATH=/app/semantic_layer.yaml

USER appuser
EXPOSE 8000

# Liveness probe hits the static /health route.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200 else 1)"

# gunicorn + uvicorn workers = a real production ASGI server (not `uvicorn --reload`).
# Tune workers/timeout via the container runtime if needed.
CMD ["gunicorn", "agentic_text_to_sql.api:app", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "2", \
     "--timeout", "60"]
