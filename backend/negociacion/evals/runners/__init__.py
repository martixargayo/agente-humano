from __future__ import annotations

from dataclasses import dataclass

from ..graders.common import EvalCaseResult


@dataclass
class EvalRunSummary:
    family: str
    total: int
    passed: int
    failed: int


def summarize_results(family: str, results: list[EvalCaseResult]) -> EvalRunSummary:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    return EvalRunSummary(family=family, total=total, passed=passed, failed=total - passed)


def print_summary(summary: EvalRunSummary) -> None:
    print(f"[{summary.family}] total={summary.total} passed={summary.passed} failed={summary.failed}")
