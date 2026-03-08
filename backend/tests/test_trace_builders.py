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
from negociacion.state.canonical_state import MemoryWorkingState
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
        recent_memory_episodic_short=[],
        trace_meta=TraceMeta(turn_id="t1", prompt_version="memory_v3", schema_version="memory_input.v1", model_target="gpt-5-nano"),
    )


def _memory_output() -> MemoryOutput:
    return MemoryOutput(
        schema_version="memory.v1",
        episodic_append=[],
        working_memory_new=MemoryWorking(current_topic=None, pending_question=None, last_turn_summary="sin cambios"),
    )


def _call(source: StructuredCallSource, refusal: str | None = None) -> StructuredCallResult:
    return StructuredCallResult(
        parsed_json=None,
        refusal=refusal,
        parse_error=None,
        exception_error=None,
        response=None,
        source=source,
    )


def test_fallback_used_only_for_real_fallback_source():
    input_payload = _memory_input()
    output_payload = _memory_output()

    fallback_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.fallback), 5, "applied")
    refusal_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.refusal, refusal="cannot"), 5, "applied")
    parse_error_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.parse_error), 5, "applied")
    exception_trace = build_memory_node_trace(input_payload, output_payload, _call(StructuredCallSource.exception), 5, "applied")

    assert fallback_trace.fallback_used is True
    assert refusal_trace.fallback_used is False
    assert parse_error_trace.fallback_used is False
    assert exception_trace.fallback_used is False
