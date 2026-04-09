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
    closure_readiness: str,
    finish_button_armed: bool,
    finish_button_latched: bool,
    provider_exception: dict[str, object | None] | None = None,
    include_provider_exception_details: bool = False,
) -> ConversationSimpleNodeTrace:
    output_summary: dict[str, object] = {
        "memory_episodic_append_count": episodic_append_count,
        "closure_readiness": closure_readiness,
        "finish_button_armed": finish_button_armed,
        "finish_button_latched": finish_button_latched,
    }
    if provider_exception is not None:
        output_summary["provider_exception_present"] = True
        if include_provider_exception_details:
            output_summary["provider_exception"] = dict(provider_exception)
    return ConversationSimpleNodeTrace(
        node_name="brain",
        model_called=model_called,
        model_attempted=model_attempted,
        model_succeeded=model_succeeded,
        latency_ms=latency_ms,
        status=status,
        fallback_reason_code=fallback_reason_code,
        input_summary={"recent_dialogue_count": recent_dialogue_count},
        output_summary=output_summary,
    )
