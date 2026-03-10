from __future__ import annotations

from negociacion.nodes.memory_node import (
    DialogueMessage,
    MemoryInput,
    MemoryOutput,
    MemoryTaskContract,
    MemoryWorking,
    TraceMeta,
    UserTurn,
)
from negociacion.state.canonical_state import MemoryWorkingState, NegotiationState, SceneState
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.builders import build_memory_node_trace
from negociacion.traces.models import StructuredCallResult


def _memory_input() -> MemoryInput:
    return MemoryInput(
        schema_version="memory_input.v1",
        task_contract=MemoryTaskContract(
            node_name="memory",
            objective="actualizar",
            completion_criteria=["ok"],
            output_schema_version="memory.v1",
        ),
        user_turn=UserTurn(
            raw_text="hola",
            normalized_text="hola",
            modality="text",
            language="es",
            timestamp_iso="2026-01-01T00:00:00Z",
        ),
        recent_dialogue_short=[DialogueMessage(role="user", text="hola")],
        memory_working_current=MemoryWorkingState(current_topic=None, pending_question=None, last_turn_summary=None),
        scene_state=SceneState(copresent=True, encounter_in_progress=True, conversation_only=True),
        recent_memory_episodic_short=[],
        trace_meta=TraceMeta(turn_id="t1", prompt_version="memory_v3", schema_version="memory_input.v1", model_target="gpt-5-nano"),
    )


def _memory_output() -> MemoryOutput:
    return MemoryOutput(
        schema_version="memory.v1",
        episodic_append=[],
        working_memory_new=MemoryWorking(current_topic=None, pending_question=None, last_turn_summary="sin cambios"),
        negotiation_state=NegotiationState(),
    )


def _call(source: StructuredCallSource, refusal: str | None = None) -> StructuredCallResult:
    return StructuredCallResult(
        parsed_json=None,
        refusal=refusal,
        parse_error=None,
        exception_error=None,
        response=None,
        source=source,
        model_called=True,
        raw_output_text='{"schema_version":"memory.v1"}',
    )


def test_fallback_applied_for_any_non_model_recovery_path():
    input_payload = _memory_input()
    output_payload = _memory_output()

    fallback_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.fallback), 5, "applied")
    refusal_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.refusal, refusal="cannot"), 5, "applied")
    parse_error_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.parse_error), 5, "applied")
    exception_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.exception), 5, "applied")

    assert fallback_trace.fallback_used is True
    assert refusal_trace.fallback_used is True
    assert parse_error_trace.fallback_used is True
    assert exception_trace.fallback_used is True
    assert fallback_trace.fallback_applied is True
    assert refusal_trace.fallback_applied is True


def test_trace_layers_and_threading_flags_are_explicit():
    trace = build_memory_node_trace(
        _memory_input(),
        _memory_output(),
        _call(StructuredCallSource.exception),
        8,
        "applied",
        threading_info={
            "threading_policy": "stateless_parallel",
            "threading_mode_effective": "stateless",
            "request_context_has_conversation_id": False,
            "request_context_has_previous_response_id": False,
        },
    )

    assert trace.model_called is True
    assert trace.validation_succeeded is False
    assert trace.fallback_applied is True
    assert trace.final_output_source == "fallback_output"
    assert trace.fallback_output_summary is not None
    assert trace.threading_policy == "stateless_parallel"
    assert trace.threading_mode_effective == "stateless"
    assert trace.request_context_has_conversation_id is False
