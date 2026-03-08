from __future__ import annotations

from typing import Any

from .common import EvalCaseResult, build_case_result, check
from .trace import get_latest_rich_trace, has_required_node_blocks


def grade_end_to_end_case(case_id: str, final_reply: str, world_state: dict[str, Any], memory_key: str, expected_checks: dict[str, Any]) -> EvalCaseResult:
    checks = []
    rich_trace = get_latest_rich_trace(world_state, memory_key)
    canonical = world_state.get(memory_key, {})

    checks.append(check("final_reply_non_empty", bool(final_reply.strip())))
    checks.append(check("rich_trace_persisted", rich_trace is not None))
    checks.append(check("canonical_trace_present", isinstance(canonical.get("trace"), dict)))

    if rich_trace is not None:
        checks.append(check("rich_trace_required_nodes", has_required_node_blocks(rich_trace)))

        expected_phase = expected_checks.get("expected_phase")
        if expected_phase:
            got_phase = (
                rich_trace.get("nodes", {})
                .get("phase_classifier", {})
                .get("output_summary", {})
                .get("current_phase")
            )
            checks.append(check("expected_phase", got_phase == expected_phase, f"expected={expected_phase} got={got_phase}"))

        expected_final_status = expected_checks.get("expected_final_status")
        if expected_final_status:
            checks.append(check("expected_final_status", rich_trace.get("final_status") == expected_final_status))

        expected_guardrail = expected_checks.get("expected_guardrail")
        if expected_guardrail is not None:
            checks.append(check("expected_guardrail", rich_trace.get("guardrails_triggered") == expected_guardrail))

    return build_case_result("end_to_end", case_id, checks)
