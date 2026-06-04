"""`python -m agentic_text_to_sql.eval [--smoke]`. Phase 6."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the text-to-SQL eval harness.")
    parser.add_argument("--smoke", action="store_true", help="Run the CI smoke subset.")
    parser.parse_args()
    raise NotImplementedError("Phase 6: run gold set and score execution accuracy")


if __name__ == "__main__":
    main()
