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
            "moderation_used": turn.get("output_moderation_used", False),
            "moderation_flags": turn.get("output_moderation_flags", []),
        },
    }
