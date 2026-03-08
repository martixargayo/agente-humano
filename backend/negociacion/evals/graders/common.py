from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    passed: bool
    details: str = ""


class EvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    grader_name: str
    case_id: str
    passed: bool
    score: float
    checks: list[CheckResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)


def build_case_result(grader_name: str, case_id: str, checks: list[CheckResult], notes: list[str] | None = None, meta: dict[str, Any] | None = None) -> EvalCaseResult:
    passed_count = sum(1 for c in checks if c.passed)
    total = max(1, len(checks))
    passed = passed_count == len(checks)
    return EvalCaseResult(
        grader_name=grader_name,
        case_id=case_id,
        passed=passed,
        score=passed_count / total,
        checks=checks,
        notes=notes or [],
        meta=meta or {},
    )


def check(name: str, condition: bool, details: str = "") -> CheckResult:
    return CheckResult(name=name, passed=condition, details=details)
