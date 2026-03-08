from __future__ import annotations

from typing import Any

from ...nodes.planner_node import PlannerOutput

from .common import EvalCaseResult, build_case_result, check


VALID_STATUSES = {"plan", "clarify", "refuse"}


PHASE_DECISION_HINTS = {
    "clima_humano": {"ask", "hold"},
    "descubrimiento_y_comprension": {"ask", "hold", "counter"},
    "propuesta_creativa": {"counter", "ask", "hold"},
    "concesiones_y_ajuste_final": {"counter", "accept", "close", "ask"},
    "formalizacion_del_acuerdo": {"close", "accept", "ask"},
}


def grade_planner_case(
    case_id: str,
    output_payload: dict[str, Any],
    expected_checks: dict[str, Any],
    allowed_decisions: list[str],
    forbidden_decisions: list[str],
    case_input: dict[str, Any] | None = None,
) -> EvalCaseResult:
    checks = []
    try:
        output = PlannerOutput.model_validate(output_payload)
        checks.append(check("output_schema_valid", True))
    except Exception as exc:
        checks.append(check("output_schema_valid", False, str(exc)))
        return build_case_result("planner", case_id, checks)

    checks.append(check("schema_version", output.schema_version == "planner.v3"))
    checks.append(check("status_valid", output.status in VALID_STATUSES))
    checks.append(check("decision_allowed", output.decision in allowed_decisions if allowed_decisions else True))
    checks.append(check("decision_not_forbidden", output.decision not in set(forbidden_decisions)))
    checks.append(check("turn_goal_non_empty", bool(output.turn_goal.strip())))

    limits = output.limits
    checks.append(check("limits_complete", limits.max_sentences > 0 and limits.max_questions >= 0))

    checks.append(check("memory_targets_is_list", isinstance(output.memory_targets, list)))
    checks.append(check("done_criteria_is_list", isinstance(output.done_criteria, list) and len(output.done_criteria) > 0))

    must_include = expected_checks.get("content_plan_must_include", [])
    combined_include = " ".join(output.content_plan.must_include).lower()
    checks.append(check("content_plan_must_include", all(token.lower() in combined_include for token in must_include)))

    must_avoid = expected_checks.get("content_plan_must_avoid", [])
    combined_avoid = " ".join(output.content_plan.must_avoid).lower()
    checks.append(check("content_plan_must_avoid", all(token.lower() in combined_avoid for token in must_avoid)))

    if case_input is not None:
        current_phase = case_input.get("current_phase") if isinstance(case_input, dict) else None
        if isinstance(current_phase, str):
            hinted = PHASE_DECISION_HINTS.get(current_phase)
            checks.append(check("decision_coherent_with_current_phase", output.decision in hinted if hinted else True, f"phase={current_phase} decision={output.decision}"))

        phase_card = case_input.get("phase_card") if isinstance(case_input, dict) else None
        phase_card_phase = phase_card.get("phase") if isinstance(phase_card, dict) else None
        if isinstance(current_phase, str) and isinstance(phase_card_phase, str):
            checks.append(check("phase_card_matches_current_phase", current_phase == phase_card_phase))

    return build_case_result("planner", case_id, checks)
