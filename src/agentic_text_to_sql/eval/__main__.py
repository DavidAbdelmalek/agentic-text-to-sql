"""`python -m agentic_text_to_sql.eval [--smoke]`.

Full run reports + exits 0. Smoke run is the CI gate: it must score 1.0 execution accuracy
(the smoke questions align with the deterministic mock fixtures), so any harness/agent
regression on the gate set fails CI.
"""

from __future__ import annotations

import argparse

from agentic_text_to_sql.eval.runner import run_eval


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the text-to-SQL eval harness.")
    parser.add_argument("--smoke", action="store_true", help="Run the CI smoke subset.")
    args = parser.parse_args()

    payload = run_eval(smoke=args.smoke)

    if args.smoke and payload["summary"]["execution_accuracy"] < 1.0:
        raise SystemExit("smoke eval failed: execution accuracy < 1.0")


if __name__ == "__main__":
    main()
