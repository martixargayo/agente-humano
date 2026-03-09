from __future__ import annotations

from sessions.state import SessionState

from negociacion.orchestration import flow_config as fc
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from negociacion.state.shared_types import StructuredCallSource


def _model(parsed_json: dict) -> fc.StructuredCallResult:
    return fc.StructuredCallResult(
        parsed_json=parsed_json,
        refusal=None,
        parse_error=None,
        exception_error=None,
        response=None,
        source=StructuredCallSource.model,
        model_called=True,
    )


def test_trace_invariants_observed_not_applied_means_output_not_changed(monkeypatch):
    session = SessionState(user_id="u_inv", session_id="s_inv")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_traces": True})

    monkeypatch.setattr(fc, "_build_client", lambda: None)

    def _fake_execute_memory_and_phase(**kwargs):
        _ = kwargs
        mem_call = _model({
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": None, "pending_question": None, "last_turn_summary": "ok"},
        })
        phase_call = _model({"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"})
        info = {"threading_policy": "stateless_parallel", "threading_mode_effective": "stateless", "request_context_has_conversation_id": False, "request_context_has_previous_response_id": False}
        return mem_call, 1, info, phase_call, 1, info, {}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, request_context, store)
        if response_model.__name__ == "PlannerOutput":
            return _model({
                "schema_version": "planner.v3",
                "status": "plan",
                "turn_goal": "ok",
                "decision": "ask",
                "content_plan": {"must_include": ["x"], "must_avoid": []},
                "limits": {"max_sentences": 2, "max_questions": 1, "allow_topic_shift": False, "allow_personal_disclosure": False},
                "memory_targets": [],
                "done_criteria": ["ok"],
            })
        return _model({
            "schema_version": "executor.v1",
            "status": "deliver",
            "spoken_text": "según el planner, 100% seguro",
            "memory_used": [],
            "refusal_reason": None,
        })

    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    _, updated = run_negotiation_cognitive_turn(session, "Hola", config)
    trace = updated.world_state[f"{config.memory_key}_traces"][0]
    executor = trace["nodes"]["executor"]

    assert trace["output_guardrail_enforcement_action"] == "observed_not_applied"
    assert trace["output_guardrail_output_changed"] is False
    assert executor["guardrail_applied"] is False
    assert executor["final_output_source"] == "validated_output"


def test_trace_invariants_fallback_has_fallback_summary_and_source(monkeypatch):
    session = SessionState(user_id="u_fb_inv", session_id="s_fb_inv")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_traces": True})

    monkeypatch.setattr(fc, "_build_client", lambda: None)

    def _fake_execute_memory_and_phase(**kwargs):
        _ = kwargs
        mem_call = _model({
            "schema_version": "memory.v1",
            "episodic_append": [],
            "working_memory_new": {"current_topic": None, "pending_question": None, "last_turn_summary": "ok"},
        })
        phase_call = _model({"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"})
        info = {"threading_policy": "stateless_parallel", "threading_mode_effective": "stateless", "request_context_has_conversation_id": False, "request_context_has_previous_response_id": False}
        return mem_call, 1, info, phase_call, 1, info, {}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, request_context, store)
        if response_model.__name__ == "PlannerOutput":
            return fc.StructuredCallResult(
                parsed_json=None,
                refusal=None,
                parse_error=None,
                exception_error="boom",
                response=None,
                source=StructuredCallSource.exception,
                model_called=True,
            )
        return _model({
            "schema_version": "executor.v1",
            "status": "clarify",
            "spoken_text": "Necesito un dato adicional para continuar.",
            "memory_used": [],
            "refusal_reason": None,
        })

    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    _, updated = run_negotiation_cognitive_turn(session, "Hola", config)
    planner = updated.world_state[f"{config.memory_key}_traces"][0]["nodes"]["planner"]

    assert planner["fallback_applied"] is True
    assert planner["fallback_output_summary"] is not None
    assert planner["final_output_source"] == "fallback_output"
