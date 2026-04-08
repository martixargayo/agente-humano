from __future__ import annotations

from .models import ConversationSimpleNodeTrace


def build_brain_node_trace(*, latency_ms: int, status: str, model_called: bool, recent_dialogue_count: int, episodic_append_count: int) -> ConversationSimpleNodeTrace:
    return ConversationSimpleNodeTrace(
        node_name="brain",
        model_called=model_called,
        latency_ms=latency_ms,
        status=status,
        input_summary={"recent_dialogue_count": recent_dialogue_count},
        output_summary={"memory_episodic_append_count": episodic_append_count},
    )
