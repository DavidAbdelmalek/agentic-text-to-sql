"""Enable Cortex cross-region inference, then probe which Claude models are reachable."""

from __future__ import annotations

from agentic_text_to_sql.db import snowflake as sf

CLAUDE_MODELS = [
    "claude-4-sonnet",
    "claude-4-opus",
    "claude-sonnet-4-5",
    "claude-3-7-sonnet",
    "claude-3-5-sonnet",
]


def main() -> None:
    con = sf.connect()  # ACCOUNTADMIN
    cur = con.cursor()

    # Allow Cortex to route to models hosted in other regions (e.g. AWS US).
    cur.execute("ALTER ACCOUNT SET CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'")
    cur.execute("SHOW PARAMETERS LIKE 'CORTEX_ENABLED_CROSS_REGION' IN ACCOUNT")
    print("cross-region:", cur.fetchone()[1])

    print("\nClaude model probe (cross-region):")
    for m in CLAUDE_MODELS:
        try:
            cur.execute("select snowflake.cortex.complete(%s, %s)", (m, "Reply with just: OK"))
            ans = str(cur.fetchone()[0]).strip().replace("\n", " ")
            print(f"  OK    {m:20} -> {ans[:50]}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {m:20} -> {str(e).splitlines()[0][:90]}")
    con.close()


if __name__ == "__main__":
    main()
