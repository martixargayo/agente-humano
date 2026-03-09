from __future__ import annotations

import json

from sessions.state import SessionState

from negociacion.nodes.memory_node import MemoryOutput
from negociacion.orchestration import flow_config as fc
from negociacion.orchestration.flow_config import (
    _build_user_turn,
    build_memory_input,
    build_negotiation_pipeline_config,
    freeze_prompt_artifacts,
    run_negotiation_cognitive_turn,
)
from negociacion.state.canonical_state import build_default_canonical_state
from negociacion.state.shared_types import StructuredCallSource, ThreadMode
from negociacion.traces.builders import build_memory_node_trace
from negociacion.traces.models import PromptArtifacts, StructuredCallResult


def _extract_between(text: str, start: str, end: str) -> str:
    s = text.index(start) + len(start)
    e = text.index(end)
    return text[s:e].strip()


def test_freeze_prompt_artifacts_is_immutable_after_input_mutation():
    state = build_default_canonical_state(session_id="s1", thread_mode=ThreadMode.conversation)
    user_turn = _build_user_turn("hola", "2026-01-01T00:00:00Z")
    trace_meta = {"turn_id": "t1", "prompt_version": "memory_v3", "schema_version": "memory_input.v1", "model_target": "gpt-5-nano"}
    memory_input = build_memory_input(state, [], user_turn, trace_meta)  # type: ignore[arg-type]

    frozen = freeze_prompt_artifacts(
        developer_prompt_text="PROMPT",
        payload=memory_input,
        render_user_prompt=lambda payload_json: f"<memory_input_json>\n{payload_json}\n</memory_input_json>",
        model_target="gpt-5-nano",
        prompt_version="memory_v3",
        input_schema_version="memory_input.v1",
        output_schema_version="memory.v1",
        threading_info={"threading_policy": "stateless_parallel", "threading_mode_effective": "stateless"},
    )

    original_payload_json = frozen.artifacts.input_payload_json
    original_rendered = frozen.artifacts.user_prompt_rendered
    original_hash = frozen.artifacts.payload_hash

    memory_input.memory_working_current.current_topic = "MUTATED"
    memory_input.user_turn.normalized_text = "MUTATED"

    assert frozen.artifacts.input_payload_json == original_payload_json
    assert frozen.artifacts.user_prompt_rendered == original_rendered
    assert frozen.artifacts.payload_hash == original_hash
    assert "MUTATED" not in (frozen.artifacts.input_payload_json or "")


def test_frozen_artifact_user_prompt_and_payload_json_are_internally_consistent():
    payload = {"a": 1, "nested": {"b": ["x", "y"]}}
    frozen = freeze_prompt_artifacts(
        developer_prompt_text="PROMPT",
        payload=payload,
        render_user_prompt=lambda payload_json: f"<planner_input_json>\n{payload_json}\n</planner_input_json>",
        model_target="o4-mini",
        prompt_version="planner_v3",
        input_schema_version="planner_input.v1",
        output_schema_version="planner.v3",
        threading_info={"threading_policy": "stateful_sequential", "threading_mode_effective": "conversation"},
    )

    embedded = _extract_between(frozen.artifacts.user_prompt_rendered or "", "<planner_input_json>", "</planner_input_json>")
    assert embedded == frozen.artifacts.input_payload_json
    assert json.loads(embedded) == json.loads(frozen.artifacts.input_payload_json or "{}")


def test_trace_builder_uses_prompt_artifacts_without_recomputing():
    input_payload = build_memory_input(
        build_default_canonical_state(session_id="s2", thread_mode=ThreadMode.conversation),
        [],
        _build_user_turn("hola", "2026-01-01T00:00:00Z"),
        {"turn_id": "t2", "prompt_version": "memory_v3", "schema_version": "memory_input.v1", "model_target": "gpt-5-nano"},  # type: ignore[arg-type]
    )
    output_payload = MemoryOutput.model_validate(
        {
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": None, "pending_question": None, "last_turn_summary": "ok"},
        }
    )
    artifacts = PromptArtifacts(
        developer_prompt_text="D",
        user_prompt_rendered="U",
        input_payload_json='{"frozen":true}',
        model_target="gpt-5-nano",
        prompt_version="memory_v3",
        input_schema_version="memory_input.v1",
        output_schema_version="memory.v1",
    )

    input_payload.user_turn.normalized_text = "mutated"
    trace = build_memory_node_trace(
        input_payload,
        output_payload,
        StructuredCallResult(parsed_json=None, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.fallback, model_called=True),
        1,
        "applied",
        prompt_artifacts=artifacts,
    )

    assert trace.prompt_artifacts is not None
    assert trace.prompt_artifacts.input_payload_json == '{"frozen":true}'


def test_e2e_hola_freezes_same_payload_for_call_and_trace_in_memory_planner_executor(monkeypatch):
    session = SessionState(user_id="u_freeze", session_id="s_freeze")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_traces": True})

    monkeypatch.setattr(fc, "_build_client", lambda: None)

    def _fake_execute_memory_and_phase(**kwargs):
        mem_messages = kwargs["memory_messages"]
        phase_messages = kwargs["phase_messages"]
        memory_payload = _extract_between(mem_messages[1]["content"], "<memory_input_json>", "</memory_input_json>")
        phase_payload = _extract_between(phase_messages[1]["content"], "<phase_classifier_input_json>", "</phase_classifier_input_json>")
        assert "MUTATED" not in memory_payload
        assert "MUTATED" not in phase_payload
        info = {"threading_policy": "stateless_parallel", "threading_mode_effective": "stateless", "request_context_has_conversation_id": False, "request_context_has_previous_response_id": False}
        mem_call = StructuredCallResult(parsed_json={"schema_version": "memory.v1", "episodic_append": [], "working_memory_new": {"current_topic": None, "pending_question": None, "last_turn_summary": "hola"}}, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True)
        phase_call = StructuredCallResult(parsed_json={"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"}, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True)
        return mem_call, 1, info, phase_call, 1, info, {}

    seen = {}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, reasoning_effort, request_context, store)
        seen[response_model.__name__] = messages[1]["content"]
        if response_model.__name__ == "PlannerOutput":
            return StructuredCallResult(parsed_json={"schema_version": "planner.v3", "status": "plan", "turn_goal": "goal", "decision": "ask", "content_plan": {"must_include": ["hola"], "must_avoid": []}, "limits": {"max_sentences": 2, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False}, "memory_targets": [], "done_criteria": ["ok"]}, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True)
        return StructuredCallResult(parsed_json={"schema_version": "executor.v1", "status": "deliver", "spoken_text": "hola", "memory_used": [], "refusal_reason": None}, refusal=None, parse_error=None, exception_error=None, response=None, source=StructuredCallSource.model, model_called=True)

    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    _, updated = run_negotiation_cognitive_turn(session, "hola", config)
    trace = updated.world_state[f"{config.memory_key}_traces"][0]

    planner_payload_call = _extract_between(seen["PlannerOutput"], "<planner_input_json>", "</planner_input_json>")
    executor_payload_call = _extract_between(seen["ExecutorOutput"], "<executor_input_json>", "</executor_input_json>")

    assert trace["nodes"]["memory"]["prompt_artifacts"]["input_payload_json"] in trace["nodes"]["memory"]["prompt_artifacts"]["user_prompt_rendered"]
    assert trace["nodes"]["planner"]["prompt_artifacts"]["input_payload_json"] == planner_payload_call
    assert trace["nodes"]["planner"]["prompt_artifacts"]["input_payload_json"] in trace["nodes"]["planner"]["prompt_artifacts"]["user_prompt_rendered"]
    assert trace["nodes"]["executor"]["prompt_artifacts"]["input_payload_json"] == executor_payload_call
    assert trace["nodes"]["executor"]["prompt_artifacts"]["input_payload_json"] in trace["nodes"]["executor"]["prompt_artifacts"]["user_prompt_rendered"]
