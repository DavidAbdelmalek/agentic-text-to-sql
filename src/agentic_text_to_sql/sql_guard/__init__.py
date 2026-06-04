"""SQL safety gate (runtime twin of the sql-guardian subagent). Static checks with
sqlglot + EXPLAIN before any execution. Phase 4 implements; see the
sql-generation-contract skill for the exact rule set."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Verdict(StrEnum):
    APPROVE = "approve"
    REPAIR = "repair"
    REJECT = "reject"


@dataclass(frozen=True)
class GuardResult:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)
    repaired_sql: str | None = None


def review(sql: str, allowed_identifiers: set[str], default_limit: int) -> GuardResult:
    """Phase 4: parse, enforce read-only/single-statement, resolve identifiers against the
    semantic layer, inject LIMIT, and stage EXPLAIN. Default posture is REJECT."""
    raise NotImplementedError("Phase 4: implement guardrail rules")
