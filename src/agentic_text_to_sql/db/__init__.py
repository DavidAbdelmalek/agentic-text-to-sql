"""Read-only database access layer. The agent reaches Postgres ONLY through here,
and ONLY via the read-only role DSN. Belt-and-braces: the client refuses non-SELECT
even though the DB role would reject it anyway."""
