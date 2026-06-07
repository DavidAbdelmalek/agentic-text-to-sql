# Windows mirror of the Makefile (no `make` on stock Windows). Usage:
#   ./tasks.ps1 install | provision | load | dbt-build | semantic | run-cli | eval | ci | ...
# The warehouse is Snowflake; credentials come from GENAI_DBT_SNOWFLAKE_* env vars.
param([Parameter(Position = 0)][string]$Target = "help", [Parameter(Position = 1)][string]$Q = "")

$ErrorActionPreference = "Stop"

switch ($Target) {
    "help"       { Get-Content Makefile | Select-String '## ' | ForEach-Object { $_.Line } }
    "install"    { uv sync --group dev }
    "provision"  { uv run python scripts/snowflake_provision.py }
    "verify-ro"  { uv run python scripts/snowflake_verify_readonly.py }
    "load"       { uv run python -m agentic_text_to_sql.ingest }
    "dbt-build"  { Push-Location dbt; uv run dbt deps; uv run dbt build; Pop-Location }
    "semantic"   { Push-Location dbt; uv run dbt docs generate; Pop-Location; uv run python scripts/generate_semantic_layer.py }
    "lint"       { uv run ruff check src tests }
    "fmt"        { uv run ruff format src tests }
    "fmt-check"  { uv run ruff format --check src tests }
    "type"       { uv run mypy }
    "test-fast"  { uv run pytest -m "not integration" }
    "test"       { uv run pytest }
    "eval"       { uv run python -m agentic_text_to_sql.eval }
    "eval-smoke" { uv run python -m agentic_text_to_sql.eval --smoke }
    "drift"      { uv run python scripts/generate_semantic_layer.py --check }
    "run-api"    { uv run uvicorn agentic_text_to_sql.api:app --reload }
    "run-cli"    { uv run ttsql ask "$Q" }
    "docker-build" { docker build -t agentic-text-to-sql . }
    "docker-run" { docker run --rm -p 8000:8000 --env-file .env agentic-text-to-sql }
    "ci"         { uv run ruff check src tests; uv run ruff format --check src tests; uv run mypy; uv run python scripts/generate_semantic_layer.py --check; uv run pytest -m "not integration" }
    default      { Write-Output "unknown target '$Target'. Run ./tasks.ps1 help" }
}
