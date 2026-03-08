from __future__ import annotations

from typing import Any

from ...nodes.executor_node import ExecutorOutput

from .common import EvalCaseResult, build_case_result, check

INTERNAL_TERMS = ["planner", "phase_card", "schema", "node", "current_phase"]


def _sentence_count(text: str) -> int:
    return len([s for s in text.replace("?", ".").replace("!", ".").split(".") if s.strip()])


def grade_executor_case(
    case_id: str,
    output_payload: dict[str, Any],
    planner_status: str,
    expected_checks: dict[str, Any],
    case_input: dict[str, Any] | None = None,
) -> EvalCaseResult:
    checks = []
    try:
        output = ExecutorOutput.model_validate(output_payload)
        checks.append(check("output_schema_valid", True))
    except Exception as exc:
        checks.append(check("output_schema_valid", False, str(exc)))
        return build_case_result("executor", case_id, checks)

    checks.append(check("schema_version", output.schema_version == "executor.v1"))
    checks.append(check("status_valid", output.status in {"deliver", "clarify", "refuse"}))

    if output.status in {"deliver", "clarify"}:
        checks.append(check("spoken_text_non_empty", bool(output.spoken_text.strip())))
    if output.status == "refuse":
        checks.append(check("refusal_reason_present", bool((output.refusal_reason or "").strip())))

    text = output.spoken_text or ""
    max_sentences = int(expected_checks.get("max_sentences", 8))
    max_questions = int(expected_checks.get("max_questions", 2))
    checks.append(check("respects_max_sentences", _sentence_count(text) <= max_sentences))
    checks.append(check("respects_max_questions", text.count("?") <= max_questions))

    lowered = text.lower()
    checks.append(check("no_internal_terms", not any(term in lowered for term in INTERNAL_TERMS)))
    checks.append(check("no_replanning_markers", "plan" not in lowered and "decisión" not in lowered))

    coherent_status = not (planner_status == "refuse" and output.status != "refuse")
    checks.append(check("coherent_with_planner_status", coherent_status, f"planner={planner_status} executor={output.status}"))

    if case_input is not None:
        planner_output = case_input.get("planner_output", {}) if isinstance(case_input, dict) else {}
        limits = case_input.get("response_limits", {}) if isinstance(case_input, dict) else {}
        if isinstance(planner_output, dict) and planner_output.get("status"):
            checks.append(check("planner_output_status_consistency", planner_output.get("status") == planner_status))
        if isinstance(limits, dict) and limits:
            checks.append(check("input_limits_shape", "max_sentences" in limits and "max_questions" in limits))

    return build_case_result("executor", case_id, checks)
