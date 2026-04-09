from __future__ import annotations

from .models import ConversationSimpleNodeTrace


def build_brain_node_trace(
    *,
    latency_ms: int,
    status: str,
    model_called: bool,
    model_attempted: bool,
    model_succeeded: bool,
    fallback_reason_code: str | None,
    recent_dialogue_count: int,
    episodic_append_count: int,
) -> ConversationSimpleNodeTrace:
    return ConversationSimpleNodeTrace(
        node_name="brain",
        model_called=model_called,
        model_attempted=model_attempted,
        model_succeeded=model_succeeded,
        latency_ms=latency_ms,
        status=status,
        fallback_reason_code=fallback_reason_code,
        input_summary={"recent_dialogue_count": recent_dialogue_count},
        output_summary={"memory_episodic_append_count": episodic_append_count},
    )
