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
        model_called=True,
    )


def _config(mode: ThreadMode) -> NegotiationTurnConfig:
    return NegotiationTurnConfig(prompts_dir="backend/negociacion/prompts", thread_mode_default=mode)


def test_execute_memory_phase_runs_parallel_and_isolates_context_even_in_conversation_mode(monkeypatch):
    canonical = build_default_canonical_state(session_id="s", thread_mode=ThreadMode.conversation)
    seen_nodes: set[str] = set()
    seen_contexts: dict[str, dict[str, str]] = {}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, store)
        node = "memory" if response_model.__name__ == "MemoryOutput" else "phase"
        seen_nodes.add(node)
        seen_contexts[node] = dict(request_context)
        return _fake_result()

    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    mem_call, _, mem_threading, phase_call, _, phase_threading, _ = _execute_memory_and_phase(
        client=None,
        config=_config(ThreadMode.conversation),
        canonical_state=canonical,
        request_context={"conversation": "conv-1"},
        memory_prompt="M",
        phase_classifier_prompt="P",
        memory_input=fc.build_memory_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="m", schema_version="memory_input.v1", model_target="x")),
        phase_input=fc.build_phase_input(canonical, [], fc._build_user_turn("hola", "2026-01-01T00:00:00Z"), fc.TraceMeta(turn_id="t", prompt_version="p", schema_version="phase_classifier_input.v1", model_target="x")),
    )

    assert seen_nodes == {"memory", "phase"}
    assert seen_contexts["memory"] == {}
    assert seen_contexts["phase"] == {}
    assert mem_call.source == StructuredCallSource.fallback
    assert phase_call.source == StructuredCallSource.fallback
    assert mem_threading["threading_policy"] == "stateless_parallel"
    assert phase_threading["threading_policy"] == "stateless_parallel"
    assert mem_threading["request_context_has_conversation_id"] is False
    assert phase_threading["request_context_has_conversation_id"] is False


def test_node_request_context_for_stateful_nodes_keeps_conversation():
    context, info = fc._node_request_context("planner", {"conversation": "conv-2"})
    assert context == {"conversation": "conv-2"}
    assert info["threading_policy"] == "stateful_sequential"
    assert info["threading_mode_effective"] == "conversation"
    assert info["request_context_has_conversation_id"] is True
