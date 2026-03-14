from __future__ import annotations

from typing import Any

from evaluacion.contracts.models import FeedbackReportCoreV1, TurnTrajectoryV1


def _collect_strict_schema_issues(node: Any, *, path: str = "root") -> list[tuple[str, str, Any]]:
    issues: list[tuple[str, str, Any]] = []
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            properties = set(node.get("properties", {}).keys())
            required = set(node.get("required", []))
            missing_required = sorted(properties - required)
            if missing_required:
                issues.append((path, "missing_required", missing_required))
            if node.get("additionalProperties") is not False:
                issues.append((path, "additional_properties_not_false", node.get("additionalProperties")))

        for key, value in node.items():
            issues.extend(_collect_strict_schema_issues(value, path=f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            issues.extend(_collect_strict_schema_issues(value, path=f"{path}[{index}]"))
    return issues


def test_feedback_report_core_v1_schema_diagnostic() -> None:
    schema = FeedbackReportCoreV1.model_json_schema()
    issues = _collect_strict_schema_issues(schema)
    assert issues == []


def test_turn_trajectory_v1_schema_diagnostic() -> None:
    schema = TurnTrajectoryV1.model_json_schema()
    issues = _collect_strict_schema_issues(schema)

    assert issues == []
