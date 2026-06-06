"""Test EACH agent node in isolation, live against Snowflake + Cortex.

Run:  uv run python scripts/test_nodes_step_by_step.py "Total revenue by country"

Nodes are plain functions: state(dict) -> partial state(dict). LangGraph normally threads the
state for you; here we do it by hand so you can watch each node's input and output. We also
call the routers so you see the branch decisions.
"""

from __future__ import annotations

import sys

from agentic_text_to_sql.agent.graph import build_default_nodes


def show(title: str, state: dict) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")
    for k, v in state.items():
        text = str(v)
        print(f"  {k:18} = {text[:90]}{'...' if len(text) > 90 else ''}")


def main() -> None:
    args = sys.argv[1:]
    nodes = build_default_nodes()  # llm=Cortex, client=read-only, full schema rendered once

    # `--schema` just dumps the schema_context fed to generate, then exits.
    if args and args[0] == "--schema":
        print("=== schema_context (fed to generate every call) ===")
        print(nodes.schema_context)
        return

    question = " ".join(args) or "Total revenue by country"
    state: dict = {"question": question, "repair_attempts": 0}
    show("START state", state)

    # 1) GENERATE — question (+ full schema) -> SQL
    out = nodes.generate(state)
    state.update(out)
    show("1. generate()  -> writes sql, retrieved_tables", out)

    # 2) GUARD — sql -> safety checks + EXPLAIN; sets/clears error
    out = nodes.guard(state)
    state.update(out)
    show("2. guard()     -> sql (maybe +LIMIT), error", out)
    print(f"\n  route_after_guard -> {nodes.route_after_guard(state)}")
    if state.get("error"):
        print("  guard FAILED — would go to repair. Stopping node walk.")
        return

    # 3) EXECUTE — sql -> rows (via read-only AGENT_RO role)
    out = nodes.execute(state)
    state.update(out)
    show("3. execute()   -> result_columns, result_rows, error", out)
    print(f"\n  route_after_execute -> {nodes.route_after_execute(state)}")
    if state.get("error"):
        print("  execute FAILED — would go to repair. Stopping node walk.")
        return

    # 4) SUMMARIZE — rows -> English answer
    out = nodes.summarize(state)
    state.update(out)
    show("4. summarize() -> answer", out)

    # --- repair / give_up demo (synthetic failing state) ------------------
    print(f"\n{'#' * 70}\n# repair + give_up demo (forced error state)\n{'#' * 70}")
    bad: dict = {"error": "boom: column foo does not exist", "repair_attempts": 0}
    for attempt in range(1, 5):
        bad.update(nodes.repair(bad))  # bumps repair_attempts
        decision = nodes.route_after_repair(bad)
        print(f"  attempt {bad['repair_attempts']}: route_after_repair -> {decision}")
        if decision == "give_up":
            bad.update(nodes.give_up(bad))
            print(f"  give_up() -> failed={bad['failed']}, answer={bad['answer'][:60]}...")
            break


if __name__ == "__main__":
    main()
