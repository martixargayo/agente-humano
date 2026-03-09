from __future__ import annotations

from ..nodes.executor_node import ExecutorInput, ExecutorOutput
from ..nodes.memory_node import MemoryInput, MemoryOutput
from ..nodes.phase_classifier_node import PhaseClassifierInput, PhaseClassifierOutput
from ..nodes.planner_node import PlannerInput, PlannerOutput
from .models import NodeInputSummary, NodeOutputSummary, PromptArtifacts, RichNodeTrace, StructuredCallResult
from ..state.canonical_state import MemoryWorkingState, PlannerState
from ..state.shared_types import NodeName, StructuredCallSource
from .constants import EXCERPT_MAX_CHARS
from .summaries import (
    ExecutorInputSummary,
    ExecutorOutputSummary,
    MemoryInputSummary,
    MemoryOutputSummary,
    MemoryWorkingSummary,
    PhaseInputSummary,
    PhaseOutputSummary,
    PlannerInputSummary,
    PlannerLimitsSummary,
    PlannerNegotiationStateSummary,
    PlannerOutputSummary,
    PlannerStateSummary,
)


def excerpt(text: str | None, max_chars: int = EXCERPT_MAX_CHARS) -> str | None:
    if text is None:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _working_summary(working: MemoryWorkingState) -> MemoryWorkingSummary:
    return MemoryWorkingSummary(
        current_topic=working.current_topic,
        pending_question=working.pending_question,
        last_turn_summary_excerpt=excerpt(working.last_turn_summary),
    )


def build_memory_node_trace(input_payload: MemoryInput, output_payload: MemoryOutput, call_result: StructuredCallResult, latency_ms: int, status: str, threading_info: dict[str, object] | None = None, prompt_artifacts: PromptArtifacts | None = None) -> RichNodeTrace:
    input_summary = MemoryInputSummary(
        user_text_excerpt=excerpt(input_payload.user_turn.normalized_text) or "",
        recent_dialogue_count=len(input_payload.recent_dialogue_short),
        memory_working_current=_working_summary(input_payload.memory_working_current),
        recent_memory_episodic_count=len(input_payload.recent_memory_episodic_short),
        recent_memory_event_types=[item.event_type for item in input_payload.recent_memory_episodic_short],
    )
    output_summary = MemoryOutputSummary(
        episodic_append_count=len(output_payload.episodic_append),
        episodic_append_event_types=[item.event_type for item in output_payload.episodic_append],
        working_memory_new=MemoryWorkingSummary(
            current_topic=output_payload.working_memory_new.current_topic,
            pending_question=output_payload.working_memory_new.pending_question,
            last_turn_summary_excerpt=excerpt(output_payload.working_memory_new.last_turn_summary),
        ),
    )
    return _build_node_trace(NodeName.memory, input_payload.trace_meta.model_target, input_payload.trace_meta.prompt_version, input_payload.schema_version, output_payload.schema_version, status, call_result, latency_ms, input_summary, output_summary, None, threading_info=threading_info, prompt_artifacts=prompt_artifacts)


def build_phase_node_trace(input_payload: PhaseClassifierInput, output_payload: PhaseClassifierOutput, call_result: StructuredCallResult, latency_ms: int, threading_info: dict[str, object] | None = None, prompt_artifacts: PromptArtifacts | None = None) -> RichNodeTrace:
    input_summary = PhaseInputSummary(
        previous_phase=input_payload.previous_phase.value if input_payload.previous_phase else None,
        recent_phase_history=[phase.value for phase in input_payload.recent_phase_history],
        recent_turn_count=len(input_payload.recent_turns),
        user_text_excerpt=excerpt(input_payload.current_user_turn.normalized_text) or "",
    )
    output_summary = PhaseOutputSummary(current_phase=output_payload.current_phase.value)
    return _build_node_trace(NodeName.phase_classifier, input_payload.trace_meta.model_target, input_payload.trace_meta.prompt_version, input_payload.schema_version, output_payload.schema_version, output_payload.current_phase.value, call_result, latency_ms, input_summary, output_summary, None, threading_info=threading_info, prompt_artifacts=prompt_artifacts)


def _planner_state_summary(planner_state: PlannerState) -> PlannerStateSummary:
    return PlannerStateSummary(
        current_phase=planner_state.current_phase.value if planner_state.current_phase else None,
        previous_phase=planner_state.previous_phase.value if planner_state.previous_phase else None,
        current_turn_goal=planner_state.current_turn_goal,
        topics_touched_current_phase_count=len(planner_state.topics_touched_current_phase),
        topics_touched_previous_phases_count=len(planner_state.topics_touched_previous_phases),
    )


def _limits_summary(max_sentences: int, max_questions: int, allow_topic_shift: bool, allow_personal_disclosure: bool) -> PlannerLimitsSummary:
    return PlannerLimitsSummary(
        max_sentences=max_sentences,
        max_questions=max_questions,
        allow_topic_shift=allow_topic_shift,
        allow_personal_disclosure=allow_personal_disclosure,
    )


def build_planner_node_trace(input_payload: PlannerInput, output_payload: PlannerOutput, call_result: StructuredCallResult, latency_ms: int, threading_info: dict[str, object] | None = None, prompt_artifacts: PromptArtifacts | None = None) -> RichNodeTrace:
    input_summary = PlannerInputSummary(
        current_phase=input_payload.current_phase.value,
        phase_card_phase=input_payload.phase_card.phase.value,
        user_text_excerpt=excerpt(input_payload.user_turn.normalized_text) or "",
        recent_dialogue_count=len(input_payload.recent_dialogue_short),
        memory_working=_working_summary(input_payload.memory_working),
        negotiation_state=PlannerNegotiationStateSummary(
            last_offer_self=input_payload.negotiation_state.last_offer_self,
            last_offer_other=input_payload.negotiation_state.last_offer_other,
            blockers_count=len(input_payload.negotiation_state.blockers),
            blockers=list(input_payload.negotiation_state.blockers),
        ),
        planner_state=_planner_state_summary(input_payload.planner_state),
        selected_memory_count=len(input_payload.selected_memory),
        selected_memory_ids=[item.memory_id for item in input_payload.selected_memory],
    )
    output_summary = PlannerOutputSummary(
        status=output_payload.status,
        decision=output_payload.decision,
        turn_goal=output_payload.turn_goal,
        must_include=list(output_payload.content_plan.must_include),
        must_avoid=list(output_payload.content_plan.must_avoid),
        limits=_limits_summary(
            output_payload.limits.max_sentences,
            output_payload.limits.max_questions,
            output_payload.limits.allow_topic_shift,
            output_payload.limits.allow_personal_disclosure,
        ),
        memory_targets=list(output_payload.memory_targets),
        done_criteria=list(output_payload.done_criteria),
    )
    return _build_node_trace(NodeName.planner, input_payload.trace_meta.model_target, input_payload.trace_meta.prompt_version, input_payload.schema_version, output_payload.schema_version, output_payload.status, call_result, latency_ms, input_summary, output_summary, None, threading_info=threading_info, prompt_artifacts=prompt_artifacts)


def build_executor_node_trace(
    input_payload: ExecutorInput,
    validated_output: ExecutorOutput,
    final_output: ExecutorOutput,
    call_result: StructuredCallResult,
    latency_ms: int,
    status: str,
    *,
    guardrail_applied: bool,
    status_before_guardrail: str,
    status_after_guardrail: str,
    threading_info: dict[str, object] | None = None,
    prompt_artifacts: PromptArtifacts | None = None,
) -> RichNodeTrace:
    input_summary = ExecutorInputSummary(
        current_phase=input_payload.current_phase.value,
        phase_card_phase=input_payload.phase_card.phase.value,
        user_text_excerpt=excerpt(input_payload.user_turn.normalized_text) or "",
        recent_dialogue_count=len(input_payload.recent_dialogue_short),
        planner_status=input_payload.planner_output.status,
        planner_decision=input_payload.planner_output.decision,
        planner_turn_goal=input_payload.planner_output.turn_goal,
        selected_memory_count=len(input_payload.selected_memory_for_reference),
        selected_memory_ids=[item.memory_id for item in input_payload.selected_memory_for_reference],
        response_limits=_limits_summary(
            input_payload.response_limits.max_sentences,
            input_payload.response_limits.max_questions,
            input_payload.response_limits.allow_topic_shift,
            input_payload.response_limits.allow_personal_disclosure,
        ),
    )
    validated_summary = ExecutorOutputSummary(
        status=validated_output.status,
        spoken_text_excerpt=excerpt(validated_output.spoken_text) or "",
        spoken_text_length=len(validated_output.spoken_text),
        memory_used=list(validated_output.memory_used),
        refusal_reason=validated_output.refusal_reason,
    )
    final_summary = ExecutorOutputSummary(
        status=final_output.status,
        spoken_text_excerpt=excerpt(final_output.spoken_text) or "",
        spoken_text_length=len(final_output.spoken_text),
        memory_used=list(final_output.memory_used),
        refusal_reason=final_output.refusal_reason,
    )
    return _build_node_trace(
        NodeName.executor,
        input_payload.trace_meta.model_target,
        input_payload.trace_meta.prompt_version,
        input_payload.schema_version,
        final_output.schema_version,
        status,
        call_result,
        latency_ms,
        input_summary,
        final_summary,
        final_output.refusal_reason,
        guardrail_applied=guardrail_applied,
        status_before_guardrail=status_before_guardrail,
        status_after_guardrail=status_after_guardrail,
        validated_output_summary=validated_summary,
        post_guardrail_output_summary=final_summary if guardrail_applied else None,
        final_emitted_output_summary=final_summary,
        threading_info=threading_info,
        prompt_artifacts=prompt_artifacts,
    )


def _parse_exception(exception_error: str | None) -> tuple[str | None, str | None]:
    if not exception_error:
        return None, None
    if ":" in exception_error:
        exc_type, msg = exception_error.split(":", 1)
        return exc_type.strip() or "Exception", msg.strip() or exception_error
    return "Exception", exception_error


def _build_node_trace(
    # NOTE: source describes model-call result; final_output_source describes emitted layer.
    node: NodeName,
    model_target: str,
    prompt_version: str,
    input_schema_version: str,
    output_schema_version: str,
    status: str,
    call_result: StructuredCallResult,
    latency_ms: int,
    input_summary: NodeInputSummary,
    output_summary: NodeOutputSummary,
    refusal_reason: str | None,
    *,
    guardrail_applied: bool = False,
    status_before_guardrail: str | None = None,
    status_after_guardrail: str | None = None,
    validated_output_summary: NodeOutputSummary | None = None,
    post_guardrail_output_summary: NodeOutputSummary | None = None,
    final_emitted_output_summary: NodeOutputSummary | None = None,
    threading_info: dict[str, object] | None = None,
    prompt_artifacts: PromptArtifacts | None = None,
) -> RichNodeTrace:
    exception_type, exception_message = _parse_exception(call_result.exception_error)
    source = call_result.source if call_result.source in set(StructuredCallSource) else StructuredCallSource.exception
    validation_succeeded = source == StructuredCallSource.model
    fallback_applied = source in {StructuredCallSource.exception, StructuredCallSource.parse_error, StructuredCallSource.refusal, StructuredCallSource.fallback}

    final_source = "validated_output" if validation_succeeded else "fallback_output"
    if guardrail_applied:
        final_source = "post_guardrail_output"

    effective_validated_summary = validated_output_summary if validated_output_summary is not None else (output_summary if validation_succeeded else None)
    fallback_summary = output_summary if fallback_applied else None
    final_summary = final_emitted_output_summary if final_emitted_output_summary is not None else output_summary

    thread = threading_info or {}

    return RichNodeTrace(
        node=node,
        node_name=node.value,
        status=status,
        source=source,
        latency_ms=latency_ms,
        model_target=model_target,
        prompt_version=prompt_version,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        fallback_used=fallback_applied,
        refusal_reason=refusal_reason or call_result.refusal,
        parse_error=call_result.parse_error,
        exception_type=exception_type,
        exception_message=exception_message,
        input_summary=input_summary,
        output_summary=output_summary,
        model_called=call_result.model_called,
        validation_succeeded=validation_succeeded,
        fallback_applied=fallback_applied,
        guardrail_applied=guardrail_applied,
        final_output_source=final_source,
        status_before_guardrail=status_before_guardrail,
        status_after_guardrail=status_after_guardrail,
        output_changed_by_guardrail=bool(guardrail_applied and status_before_guardrail != status_after_guardrail),
        raw_model_output_excerpt=excerpt(call_result.raw_output_text),
        validated_output_summary=effective_validated_summary,
        fallback_output_summary=fallback_summary,
        post_guardrail_output_summary=post_guardrail_output_summary,
        final_emitted_output_summary=final_summary,
        threading_policy=thread.get("threading_policy"),
        threading_mode_effective=thread.get("threading_mode_effective"),
        request_context_has_conversation_id=bool(thread.get("request_context_has_conversation_id", False)),
        request_context_has_previous_response_id=bool(thread.get("request_context_has_previous_response_id", False)),
        prompt_artifacts=prompt_artifacts,
    )
