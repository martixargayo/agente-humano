from __future__ import annotations

from negociacion.orchestration import flow_config as fc
from negociacion.orchestration.flow_config import (
    NegotiationTurnConfig,
    StructuredCallResult,
    _execute_memory_and_phase,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import StructuredCallSource, ThreadMode


def _fake_result() -> StructuredCallResult:
    return StructuredCallResult(
        parsed_json=None,
        refusal=None,
        parse_error=None,
        exception_error="fallback",
        response=None,
        source=StructuredCallSource.fallback,
    )


def _config(mode: ThreadMode) -> NegotiationTurnConfig:
    return NegotiationTurnConfig(prompts_dir="backend/negociacion/prompts", thread_mode_default=mode)


def test_execute_memory_phase_is_sequential_for_previous_response_id(monkeypatch):
    canonical = build_default_canonical_state(session_id="s", thread_mode=ThreadMode.previous_response_id)
    order: list[str] = []

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, response_model, reasoning_effort, request_context, store)
        order.append("memory" if response_model.__name__ == "MemoryOutput" else "phase")
        return _fake_result()

    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    _execute_memory_and_phase(
        client=None,
        config=_config(ThreadMode.previous_response_id),
        canonical_state=canonical,
        request_context={},
        memory_prompt="M",
        phase_classifier_prompt="P",
        memory_input=fc.build_memory_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="m", schema_version="memory_input.v1", model_target="x")),
        phase_input=fc.build_phase_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="p", schema_version="phase_classifier_input.v1", model_target="x")),
    )

    assert order == ["memory", "phase"]


def test_execute_memory_phase_runs_both_calls_in_conversation_mode(monkeypatch):
    canonical = build_default_canonical_state(session_id="s", thread_mode=ThreadMode.conversation)
    seen_nodes: set[str] = set()

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, response_model, reasoning_effort, request_context, store)
        seen_nodes.add("memory" if response_model.__name__ == "MemoryOutput" else "phase")
        return _fake_result()

    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    _execute_memory_and_phase(
        client=None,
        config=_config(ThreadMode.conversation),
        canonical_state=canonical,
        request_context={},
        memory_prompt="M",
        phase_classifier_prompt="P",
        memory_input=fc.build_memory_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="m", schema_version="memory_input.v1", model_target="x")),
        phase_input=fc.build_phase_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="p", schema_version="phase_classifier_input.v1", model_target="x")),
    )

    assert seen_nodes == {"memory", "phase"}
