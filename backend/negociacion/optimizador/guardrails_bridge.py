from __future__ import annotations

from typing import Any


def summarize_guardrails(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": {
            "decision": turn.get("input_guardrail_decision"),
            "reasons": turn.get("input_guardrail_reasons", []),
            "triggered": turn.get("input_guardrail_triggered", False),
            "moderation_used": turn.get("input_moderation_used", False),
            "moderation_flags": turn.get("input_moderation_flags", []),
        },
        "output": {
            "decision": turn.get("output_guardrail_decision"),
            "reasons": turn.get("output_guardrail_reasons", []),
            "triggered": turn.get("output_guardrail_triggered", False),
            "status_before": turn.get("output_guardrail_status_before"),
            "status_after": turn.get("output_guardrail_status_after"),
            "rewrite_applied": turn.get("output_guardrail_rewrite_applied", False),
            "enforcement_mode": turn.get("output_guardrail_enforcement_mode", "observe_only"),
            "enforcement_action": turn.get("output_guardrail_enforcement_action", "none"),
            "observed_not_applied_rules": turn.get("output_guardrail_observed_not_applied_rules", []),
            "enforced_rules": turn.get("output_guardrail_enforced_rules", []),
            "output_changed": turn.get("output_guardrail_output_changed", False),
            "moderation_used": turn.get("output_moderation_used", False),
            "moderation_flags": turn.get("output_moderation_flags", []),
        },
    }
