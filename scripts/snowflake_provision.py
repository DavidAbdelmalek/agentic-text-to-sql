"""Provision the Snowflake objects the project needs, idempotently, as the build role.

Creates two schemas in the existing database (RAW load + curated MARTS), a read-only AGENT_RO
role granted SELECT on the marts schema only (current + future tables/views) plus the Cortex
usage database role, and grants AGENT_RO to the developer user so the agent can `USE ROLE` it.

This is the Snowflake equivalent of the Postgres read-only-role init script — the hard safety
boundary, as code. Run once after the account creds are available; safe to re-run.
"""

from __future__ import annotations

import os

from agentic_text_to_sql.db import snowflake as sf


def main() -> None:
    db = sf.database()
    raw, marts, role = sf.RAW_SCHEMA, sf.MARTS_SCHEMA, sf.AGENT_ROLE
    wh = os.environ["GENAI_DBT_SNOWFLAKE_WAREHOUSE_DEVELOPER"]
    user = os.environ["GENAI_DBT_SNOWFLAKE_USER_DEVELOPER"]

    stmts = [
        # Schemas
        f"CREATE SCHEMA IF NOT EXISTS {db}.{raw}",
        f"CREATE SCHEMA IF NOT EXISTS {db}.{marts}",
        # Read-only role
        f"CREATE ROLE IF NOT EXISTS {role} COMMENT='Read-only role for the text-to-SQL agent'",
        # Compute + read access to the MARTS schema only (never RAW)
        f"GRANT USAGE ON WAREHOUSE {wh} TO ROLE {role}",
        f"GRANT USAGE ON DATABASE {db} TO ROLE {role}",
        f"GRANT USAGE ON SCHEMA {db}.{marts} TO ROLE {role}",
        f"GRANT SELECT ON ALL TABLES IN SCHEMA {db}.{marts} TO ROLE {role}",
        f"GRANT SELECT ON FUTURE TABLES IN SCHEMA {db}.{marts} TO ROLE {role}",
        f"GRANT SELECT ON ALL VIEWS IN SCHEMA {db}.{marts} TO ROLE {role}",
        f"GRANT SELECT ON FUTURE VIEWS IN SCHEMA {db}.{marts} TO ROLE {role}",
        # Cortex usage so the agent's read-only role can call SNOWFLAKE.CORTEX.COMPLETE
        f"GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE {role}",
        # Let the developer user assume the read-only role
        f"GRANT ROLE {role} TO USER {user}",
    ]

    con = sf.connect()  # build role (ACCOUNTADMIN)
    cur = con.cursor()
    for s in stmts:
        cur.execute(s)
        print(f"  ok: {s[:80]}")
    con.close()
    print(f"\nprovision OK -> schemas {db}.{raw} + {db}.{marts}, read-only role {role} ready.")


if __name__ == "__main__":
    main()
