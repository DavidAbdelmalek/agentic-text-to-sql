# Windows mirror of the Makefile (no `make` on stock Windows). Usage:
#   ./tasks.ps1 up | install | lint | type | test-fast | eval-smoke | ...
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"

switch ($Target) {
    "help"       { Get-Content Makefile | Select-String '## ' | ForEach-Object { $_.Line } }
    "install"    { uv sync --all-extras --group dev }
    "up"         { docker compose up -d }
    "obs-up"     { docker compose --profile observability up -d }
    "down"       { docker compose --profile observability down }
    "logs"       { docker compose logs -f warehouse }
    "psql"       { $dsn = if ($env:AGENT_DATABASE_URL) { $env:AGENT_DATABASE_URL } else { "postgresql://agent_ro:agent_ro_pw@localhost:5432/warehouse" }; psql $dsn }
    "load"       { uv run python -m agentic_text_to_sql.ingest }
    "dbt-build"  { Push-Location dbt; uv run dbt deps; uv run dbt build; Pop-Location }
    "introspect" { uv run python scripts/introspect_schema.py }
    "semantic"   { uv run python -m agentic_text_to_sql.semantic_layer.build }
    "lint"       { uv run ruff check src tests }
    "fmt"        { uv run ruff format src tests }
    "type"       { uv run mypy }
    "test-fast"  { uv run pytest -m "not integration" }
    "test"       { uv run pytest }
    "eval"       { uv run python -m agentic_text_to_sql.eval }
    "eval-smoke" { uv run python -m agentic_text_to_sql.eval --smoke }
    "run-api"    { uv run uvicorn agentic_text_to_sql.api:app --reload }
    "ci"         { uv run ruff check src tests; uv run mypy; uv run pytest -m "not integration" }
    default      { Write-Output "unknown target '$Target'. Run ./tasks.ps1 help" }
}
