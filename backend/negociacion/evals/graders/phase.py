from __future__ import annotations

from typing import Any

from ...nodes.phase_classifier_node import PhaseClassifierOutput

from .common import EvalCaseResult, build_case_result, check


def grade_phase_case(case_id: str, output_payload: dict[str, Any], expected_phase: str) -> EvalCaseResult:
    checks = []
    try:
        output = PhaseClassifierOutput.model_validate(output_payload)
        checks.append(check("output_schema_valid", True))
        checks.append(check("phase_exact_match", output.current_phase.value == expected_phase, f"expected={expected_phase} got={output.current_phase.value}"))
    except Exception as exc:
        checks.append(check("output_schema_valid", False, str(exc)))
    return build_case_result("phase_classifier", case_id, checks)
