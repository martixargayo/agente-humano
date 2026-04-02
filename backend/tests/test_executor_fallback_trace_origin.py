from __future__ import annotations

from sessions.state import SessionState

from negociacion.orchestration.flow_config import build_negotiation_pipeline_config, run_negotiation_cognitive_turn
from negociacion.state.shared_types import StructuredCallSource
from negociacion.traces.models import StructuredCallResult


def _fake_call_structured(*args, **kwargs) -> StructuredCallResult:
    response_model = kwargs.get("response_model")
    if response_model is None and len(args) >= 6:
        response_model = args[5]
    name = getattr(response_model, "__name__", "")

    if name == "MemoryOutput":
        return StructuredCallResult(
            parsed_json={
                "schema_version": "memory.v1",
                "episodic_append": [],
                "working_memory_new": {
                    "current_topic": None,
                    "pending_question": None,
                    "last_turn_summary": "sin cambios",
                },
                "negotiation_state": {
                    "status": "inactive",
                    "active_axes": [],
                    "last_offer_self": None,
                    "last_offer_other": None,
                    "tentative_agreement": None,
                    "stall_state": {
                        "is_hard_stalemate": False,
                        "stalemate_reason": None,
                        "self_ultimatum_active": False,
                        "self_ultimatum_summary": None,
                    },
                    "blockers": [],
                    "next_open_loop": None,
                },
            },
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
            model_called=True,
            raw_output_text="{}",
        )

    if name == "PhaseClassifierOutput":
        return StructuredCallResult(
            parsed_json={"schema_version": "phase_classifier.v1", "current_phase": "clima_humano"},
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
            model_called=True,
            raw_output_text="{}",
        )

    if name == "PlannerOutput":
        return StructuredCallResult(
            parsed_json={
                "schema_version": "planner.v3",
                "status": "plan",
                "turn_goal": "saludar y abrir conversación",
                "decision": "ask",
                "content_plan": {"must_include": ["saludo"], "must_avoid": ["inventar hechos"]},
                "limits": {
                    "max_sentences": 2,
                    "max_questions": 1,
                    "allow_topic_shift": False,
                    "allow_personal_disclosure": False,
                },
                "memory_targets": [],
                "done_criteria": ["saludo_emitido"],
            },
            refusal=None,
            parse_error=None,
            exception_error=None,
            response=None,
            source=StructuredCallSource.model,
            model_called=True,
            raw_output_text="{}",
        )

    # executor
    return StructuredCallResult(
        parsed_json=None,
        refusal=None,
        parse_error=None,
        exception_error="500 server_error",
        response=None,
        source=StructuredCallSource.exception,
        model_called=True,
        raw_output_text=None,
    )


def test_trace_marks_executor_fallback_as_final_origin(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.orchestration.flow_config._call_structured", _fake_call_structured)

    state = SessionState(user_id="u_fallback", session_id="s_fallback")
    config = build_negotiation_pipeline_config(context_id="sala_reuniones")

    reply, updated = run_negotiation_cognitive_turn(state, "hola", config)
    trace = updated.world_state[f"{config.memory_key}_traces"][-1]

    assert trace["final_output_source"] == "executor_fallback"
    assert trace["final_output_origin"] == "executor_fallback"
    assert trace["nodes"]["executor"]["final_output_source"] == "fallback_output"
    assert "clara y directa" not in reply.lower()
