"""Prove the AGENT_RO role is read-only: writes denied, SELECT + Cortex allowed."""

from __future__ import annotations

from agentic_text_to_sql.config import get_settings
from agentic_text_to_sql.db import snowflake as sf


def main() -> None:
    con = sf.connect(role=sf.AGENT_ROLE, schema=sf.MARTS_SCHEMA)
    cur = con.cursor()

    cur.execute("select current_role()")
    print("role:", cur.fetchone()[0])

    print("\n=== writes must be DENIED ===")
    for stmt in (
        f"CREATE TABLE {sf.database()}.{sf.MARTS_SCHEMA}.evil (x int)",
        f"CREATE SCHEMA {sf.database()}.hack",
    ):
        try:
            cur.execute(stmt)
            print(f"  !! ALLOWED (bad): {stmt[:50]}")
        except Exception as e:  # noqa: BLE001
            print(f"  denied (good): {str(e).splitlines()[0][:80]}")

    print("\n=== reads + Cortex must WORK ===")
    cur.execute("select 1+1")
    print("  select ok:", cur.fetchone()[0])
    cur.execute("select ai_complete(%s, %s)", (get_settings().cortex_model, "Say OK"))
    print("  cortex ok:", str(cur.fetchone()[0]).strip()[:40])
    con.close()


if __name__ == "__main__":
    main()
