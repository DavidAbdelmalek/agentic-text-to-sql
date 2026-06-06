"""One-off probe: confirm Snowflake connectivity + which Cortex LLMs work in this region."""

from __future__ import annotations

from agentic_text_to_sql.db import snowflake as sf

MODELS = [
    "claude-3-5-sonnet",
    "claude-3-7-sonnet",
    "llama3.1-70b",
    "llama3.1-8b",
    "mistral-large2",
    "snowflake-arctic",
    "mixtral-8x7b",
]


def main() -> None:
    con = sf.connect()
    cur = con.cursor()
    cur.execute(
        "select current_version(), current_account(), current_region(), "
        "current_role(), current_warehouse(), current_database()"
    )
    print("IDENTITY:", cur.fetchone())

    print("\nCortex model probe:")
    for m in MODELS:
        try:
            cur.execute("select snowflake.cortex.complete(%s, %s)", (m, "Reply with just: OK"))
            ans = str(cur.fetchone()[0]).strip().replace("\n", " ")
            print(f"  OK    {m:18} -> {ans[:50]}")
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  {m:18} -> {str(e).splitlines()[0][:90]}")

    con.close()


if __name__ == "__main__":
    main()
