"""Schema introspection — the deterministic, non-interactive alternative to the postgres-ro
MCP server. Connects with the READ-ONLY role (introspection is itself read-only, which is the
point) and dumps tables / columns / types / primary keys / foreign keys for the public schema
to data/semantic/raw_schema.json.

The schema-explorer subagent turns this raw structure into the curated semantic layer
(business descriptions + joinable paths). Run via `make introspect`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import psycopg

from agentic_text_to_sql.config import get_settings

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "semantic" / "raw_schema.json"

# Only the curated marts (dims + fact). Staging views are excluded — the agent must never
# see them, and the read-only role can't see the `raw` schema at all.
INCLUDE_PREFIXES = ("dim_", "fct_")


def _introspect(conn: psycopg.Connection[Any]) -> dict[str, Any]:
    tables: dict[str, Any] = {}

    cols = conn.execute(
        """
        select table_name, column_name, data_type, ordinal_position
        from information_schema.columns
        where table_schema = 'public'
        order by table_name, ordinal_position
        """
    ).fetchall()
    for table_name, column_name, data_type, _ in cols:
        if not table_name.startswith(INCLUDE_PREFIXES):
            continue
        tables.setdefault(
            table_name, {"columns": [], "primary_key": [], "foreign_keys": []}
        )
        tables[table_name]["columns"].append({"name": column_name, "type": data_type})

    # Primary and foreign keys from the catalog.
    keys = conn.execute(
        """
        select
            tc.table_name,
            tc.constraint_type,
            kcu.column_name,
            ccu.table_name  as ref_table,
            ccu.column_name as ref_column
        from information_schema.table_constraints tc
        join information_schema.key_column_usage kcu
            on tc.constraint_name = kcu.constraint_name
           and tc.table_schema = kcu.table_schema
        left join information_schema.constraint_column_usage ccu
            on tc.constraint_name = ccu.constraint_name
           and tc.constraint_type = 'FOREIGN KEY'
        where tc.table_schema = 'public'
          and tc.constraint_type in ('PRIMARY KEY', 'FOREIGN KEY')
        order by tc.table_name
        """
    ).fetchall()
    for table_name, ctype, column_name, ref_table, ref_column in keys:
        if table_name not in tables:
            continue
        if ctype == "PRIMARY KEY":
            tables[table_name]["primary_key"].append(column_name)
        elif ctype == "FOREIGN KEY":
            tables[table_name]["foreign_keys"].append(
                {"column": column_name, "ref_table": ref_table, "ref_column": ref_column}
            )

    return {"schema": "public", "tables": tables}


def main() -> None:
    settings = get_settings()
    with psycopg.connect(settings.agent_database_url) as conn:
        result = _introspect(conn)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    n_tables = len(result["tables"])
    n_cols = sum(len(t["columns"]) for t in result["tables"].values())
    print(f"introspect OK -> {OUT_PATH}  ({n_tables} tables, {n_cols} columns)")


if __name__ == "__main__":
    main()
