#!/bin/bash
# ===========================================================================
# THE read-only role. This is the hard security boundary of the whole system.
#
# The LLM agent connects ONLY as this role. It can SELECT and EXPLAIN. It
# physically cannot DROP/DELETE/UPDATE/INSERT/ALTER/CREATE — Postgres rejects
# those at the engine level regardless of what SQL an LLM dreams up.
#
# Why this matters (interview answer): prompt-level "please don't write" is not
# a control — an attacker or a confused model can bypass a prompt. A revoked
# privilege cannot be talked around. Defense-in-depth runs prompt -> sql_guard
# static checks + EXPLAIN -> THIS role. The first two can fail open; this can't.
#
# Runs once on first cluster init, as superuser. Reads AGENT_DB_USER /
# AGENT_DB_PASSWORD from the container environment (set in docker-compose.yml).
# ===========================================================================
set -euo pipefail

AGENT_USER="${AGENT_DB_USER:-agent_ro}"
AGENT_PW="${AGENT_DB_PASSWORD:-agent_ro_pw}"
# Escape single quotes for the SQL string literal.
AGENT_PW_SQL="'${AGENT_PW//\'/\'\'}'"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
    -- LOGIN role, no superuser, cannot create DBs or roles.
    CREATE ROLE "$AGENT_USER" LOGIN PASSWORD $AGENT_PW_SQL
        NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

    -- Connect + read the public schema where dbt builds the star schema.
    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$AGENT_USER";
    GRANT USAGE  ON SCHEMA public TO "$AGENT_USER";

    -- Read access to whatever exists now...
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO "$AGENT_USER";

    -- ...and, critically, to whatever dbt builds LATER. Tables don't exist yet
    -- at init time; DEFAULT PRIVILEGES auto-grants SELECT on future tables so no
    -- re-grant step is needed after a dbt build.
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "$AGENT_USER";

    -- Assert NO write/DDL grants (roles get none by default; we make it explicit).
    REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
        ON ALL TABLES IN SCHEMA public FROM "$AGENT_USER";
    REVOKE CREATE ON SCHEMA public FROM "$AGENT_USER";
EOSQL

echo "read-only role '$AGENT_USER' created with SELECT + EXPLAIN only."
