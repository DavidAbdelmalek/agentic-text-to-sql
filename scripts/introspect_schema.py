"""Fallback schema introspection (when the postgres-ro MCP server can't run
non-interactively). Connects with the read-only role, dumps tables/columns/keys to
data/semantic/raw_schema.json, which the schema-explorer subagent turns into the
semantic layer. Phase 3."""

from __future__ import annotations


def main() -> None:
    raise NotImplementedError("Phase 3: introspect via read-only role -> raw_schema.json")


if __name__ == "__main__":
    main()
