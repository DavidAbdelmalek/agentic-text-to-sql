"""SQL safety gate (runtime twin of the sql-guardian subagent). Static checks with sqlglot
before any execution; EXPLAIN is run separately by the graph's guard node. Rule set mirrors
the `sql-generation-contract` skill. Default posture is REJECT.

Layered safety reminder: this is fast, explainable defense-in-depth in front of the
read-only Postgres role. The role is the hard guarantee; this catches problems earlier and
with better messages (and feeds the repair loop)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

# Anything in this set anywhere in the tree => not read-only => REJECT.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Into,
)


class Verdict(StrEnum):
    APPROVE = "approve"
    REPAIR = "repair"
    REJECT = "reject"


@dataclass(frozen=True)
class GuardResult:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    repaired_sql: str | None = None


def _unknown_identifiers(stmt: exp.Expression, allowed: set[str]) -> list[str]:
    """Tables/columns referenced by the query that are not in the semantic layer. This is the
    anti-hallucination check — a generated column that doesn't exist is caught here.

    Names the query introduces itself are legal even though they aren't in the semantic layer:
    SELECT aliases (so `ORDER BY <alias>` / `HAVING <alias>` resolve) and CTE names (referenced
    in a later FROM). Without this, a perfectly valid `SUM(x) AS total ... ORDER BY total` is
    falsely rejected, which then burns the whole repair budget."""
    local: set[str] = {a.alias for a in stmt.find_all(exp.Alias) if a.alias}
    local |= {c.alias_or_name for c in stmt.find_all(exp.CTE)}

    bad: list[str] = []
    for table in stmt.find_all(exp.Table):
        if table.name and table.name not in allowed and table.name not in local:
            bad.append(table.name)
    for col in stmt.find_all(exp.Column):
        # Skip stars (SELECT *) and unqualified function output; check the bare column name.
        if isinstance(col.this, exp.Star):
            continue
        if col.name and col.name not in allowed and col.name not in local:
            bad.append(col.name)
    return sorted(set(bad))


def review(sql: str, allowed_identifiers: set[str], default_limit: int) -> GuardResult:
    reasons: list[str] = []

    # 1. Parseable?
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except ParseError as e:
        return GuardResult(Verdict.REJECT, [f"unparseable SQL: {e}"])

    # 2. Exactly one statement.
    if len(statements) != 1 or statements[0] is None:
        return GuardResult(Verdict.REJECT, ["exactly one statement is allowed"])
    stmt = statements[0]

    # 3. Read-only shape.
    if not isinstance(stmt, exp.Select | exp.Union | exp.Subquery):
        return GuardResult(Verdict.REJECT, [f"not a SELECT (got {type(stmt).__name__})"])
    for node in stmt.walk():
        if isinstance(node, _FORBIDDEN):
            return GuardResult(
                Verdict.REJECT, [f"forbidden, non-read-only element: {type(node).__name__}"]
            )

    # 4. Identifier resolution (anti-hallucination).
    unknown = _unknown_identifiers(stmt, allowed_identifiers)
    if unknown:
        return GuardResult(
            Verdict.REJECT,
            [f"unknown identifier(s) not in the semantic layer: {', '.join(unknown)}"],
        )

    # 5. Row limit present? If not, repair by injecting the default.
    if stmt.args.get("limit") is None:
        repaired = stmt.copy().limit(default_limit)
        return GuardResult(
            Verdict.REPAIR,
            [f"no LIMIT present; injected LIMIT {default_limit}"],
            repaired_sql=repaired.sql(dialect="postgres"),
        )

    return GuardResult(Verdict.APPROVE, reasons)
