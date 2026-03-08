from __future__ import annotations

from sessions.state import SessionState

from negociacion.orchestration import flow_config as fc
from negociacion.orchestration.flow_config import (
    StructuredCallResult,
    build_negotiation_pipeline_config,
    run_negotiation_cognitive_turn,
)
from negociacion.state.shared_types import NodeName, StructuredCallSource, ThreadMode


def _fake_model_result(parsed_json: dict, response_obj: object | None = None) -> StructuredCallResult:
    return StructuredCallResult(
        parsed_json=parsed_json,
        refusal=None,
        parse_error=None,
        exception_error=None,
        response=response_obj,
        source=StructuredCallSource.model,
    )


def test_e2e_pipeline_wires_nodes_and_persists_trace_and_state(monkeypatch):
    session = SessionState(user_id="u_e2e", session_id="s_e2e")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False, "feature_traces": True})

    call_order: list[str] = []

    def _fake_build_client():
        return object()

    def _fake_refresh_request_context(client, canonical_state, mode_default):
        _ = (client, mode_default)
        if canonical_state.openai_thread.thread_mode == ThreadMode.conversation:
            return {"conversation": "conv-test"}
        return {"previous_response_id": "resp-test"}

    def _fake_execute_memory_and_phase(**kwargs):
        call_order.append("memory_phase")
        memory_input = kwargs["memory_input"]
        phase_input = kwargs["phase_input"]

        assert memory_input.user_turn.normalized_text == "Necesito mover esto"
        assert phase_input.current_user_turn.normalized_text == "Necesito mover esto"

        mem_call = _fake_model_result(
            {
                "schema_version": "memory.v1",
                "episodic_append": [
                    {
                        "event_type": "important_fact",
                        "event_summary": "dato clave detectado",
                        "turn_id": "t1",
                    }
                ],
                "working_memory_new": {
                    "current_topic": "precio",
                    "pending_question": "¿confirmas presupuesto?",
                    "last_turn_summary": "resumen memoria",
                },
            }
        )
        phase_call = _fake_model_result(
            {
                "schema_version": "phase_classifier.v1",
                "current_phase": "propuesta_creativa",
            }
        )
        return mem_call, 7, phase_call, 9, {"conversation": "conv-test-2"}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, messages, reasoning_effort, store)
        if response_model.__name__ == "PlannerOutput":
            call_order.append("planner")
            assert request_context == {"conversation": "conv-test-2"}
            return _fake_model_result(
                {
                    "schema_version": "planner.v3",
                    "status": "plan",
                    "turn_goal": "cerrar siguiente paso",
                    "decision": "counter",
                    "content_plan": {"must_include": ["usar memoria"], "must_avoid": ["inventar"]},
                    "limits": {
                        "max_sentences": 2,
                        "max_questions": 1,
                        "allow_topic_shift": False,
                        "allow_personal_disclosure": False,
                    },
                    "memory_targets": ["episodic_0"],
                    "done_criteria": ["ok"],
                }
            )
        if response_model.__name__ == "ExecutorOutput":
            call_order.append("executor")
            payload_text = messages[1]["content"]
            assert '"turn_goal":"cerrar siguiente paso"' in payload_text
            return _fake_model_result(
                {
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "spoken_text": "RESPUESTA FINAL DESDE EXECUTOR",
                    "memory_used": ["episodic_0"],
                    "refusal_reason": None,
                }
            )
        raise AssertionError(f"Unexpected response_model: {response_model.__name__}")

    monkeypatch.setattr(fc, "_build_client", _fake_build_client)
    monkeypatch.setattr(fc, "refresh_request_context", _fake_refresh_request_context)
    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    reply, updated = run_negotiation_cognitive_turn(session, "Necesito mover esto", config)

    assert call_order == ["memory_phase", "planner", "executor"]
    assert reply == "RESPUESTA FINAL DESDE EXECUTOR"
    assert updated.history[-1]["role"] == "assistant"
    assert updated.history[-1]["content"] == "RESPUESTA FINAL DESDE EXECUTOR"

    memory_key = config.memory_key
    canonical = updated.world_state[memory_key]
    assert canonical["memory_working"]["last_turn_summary"] == "resumen memoria"
    assert canonical["memory_episodic"][-1]["event_summary"] == "dato clave detectado"
    assert canonical["planner_state"]["current_phase"] == "propuesta_creativa"
    assert canonical["planner_state"]["current_turn_goal"] == "cerrar siguiente paso"

    trace = canonical["trace"]
    assert trace["last_node_statuses"][NodeName.memory.value] == "applied"
    assert trace["last_node_statuses"][NodeName.phase_classifier.value] == "propuesta_creativa"
    assert trace["last_node_statuses"][NodeName.planner.value] == "plan"
    assert trace["last_node_statuses"][NodeName.executor.value] == "deliver"
    assert canonical["session"]["updated_at"]

    traces = updated.world_state[f"{memory_key}_traces"]
    assert len(traces) == 1
    assert [log["node"] for log in traces[0]["logs"]] == [
        NodeName.memory.value,
        NodeName.phase_classifier.value,
        NodeName.planner.value,
        NodeName.executor.value,
    ]


def test_turn_trace_rich_schema_for_grading_and_compact_canonical_trace(monkeypatch):
    session = SessionState(user_id="u_trace", session_id="s_trace")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False, "feature_traces": True})

    def _fake_build_client():
        return object()

    def _fake_refresh_request_context(client, canonical_state, mode_default):
        _ = (client, canonical_state, mode_default)
        return {"conversation": "conv-trace"}

    def _fake_execute_memory_and_phase(**kwargs):
        _ = kwargs
        mem_call = _fake_model_result(
            {
                "schema_version": "memory.v1",
                "episodic_append": [
                    {"event_type": "important_fact", "event_summary": "dato memoria", "turn_id": "t0"}
                ],
                "working_memory_new": {
                    "current_topic": "precio",
                    "pending_question": "¿encaja?",
                    "last_turn_summary": "resumen de salida",
                },
            }
        )
        phase_call = _fake_model_result({"schema_version": "phase_classifier.v1", "current_phase": "propuesta_creativa"})
        return mem_call, 11, phase_call, 13, {"conversation": "conv-trace"}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, request_context, store)
        if response_model.__name__ == "PlannerOutput":
            return _fake_model_result(
                {
                    "schema_version": "planner.v3",
                    "status": "plan",
                    "turn_goal": "avanzar cierre",
                    "decision": "counter",
                    "content_plan": {"must_include": ["punto A"], "must_avoid": ["punto B"]},
                    "limits": {
                        "max_sentences": 3,
                        "max_questions": 1,
                        "allow_topic_shift": False,
                        "allow_personal_disclosure": False,
                    },
                    "memory_targets": ["episodic_0"],
                    "done_criteria": ["ok"],
                }
            )
        if response_model.__name__ == "ExecutorOutput":
            return _fake_model_result(
                {
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "spoken_text": "Respuesta corta para el usuario",
                    "memory_used": ["episodic_0"],
                    "refusal_reason": None,
                }
            )
        raise AssertionError("unexpected model")

    monkeypatch.setattr(fc, "_build_client", _fake_build_client)
    monkeypatch.setattr(fc, "refresh_request_context", _fake_refresh_request_context)
    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    run_negotiation_cognitive_turn(session, "Necesito una propuesta", config)

    memory_key = config.memory_key
    canonical = session.world_state[memory_key]
    trace = session.world_state[f"{memory_key}_traces"][0]

    assert set(canonical["trace"].keys()) == {"turn_id", "last_node_statuses", "last_fallbacks", "last_refusals"}

    assert {
        "trace_version",
        "turn_id",
        "session_id",
        "user_id",
        "avatar_id",
        "thread_mode",
        "turn_started_at",
        "turn_finished_at",
        "total_latency_ms",
        "conversation_id_before",
        "conversation_id_after",
        "previous_response_id_before",
        "previous_response_id_after",
        "user_turn",
        "final_reply_text",
        "final_reply_excerpt",
        "final_status",
        "assistant_turn_emitted",
        "guardrails_triggered",
        "guardrail_reasons",
        "guardrail_rewrite_applied",
        "guardrail_status_before",
        "guardrail_status_after",
        "logs",
        "nodes",
    }.issubset(trace.keys())

    assert set(trace["nodes"].keys()) == {"memory", "phase_classifier", "planner", "executor"}
    assert [log["node_name"] for log in trace["logs"]] == ["memory", "phase_classifier", "planner", "executor"]
    assert trace["logs"][0]["status"] == trace["nodes"]["memory"]["status"]

    memory_node = trace["nodes"]["memory"]
    assert {"source", "latency_ms", "prompt_version", "input_schema_version", "output_schema_version", "input_summary", "output_summary"}.issubset(memory_node.keys())
    assert set(memory_node["input_summary"].keys()) == {
        "user_text_excerpt",
        "recent_dialogue_count",
        "memory_working_current",
        "recent_memory_episodic_count",
        "recent_memory_event_types",
    }
    assert set(memory_node["output_summary"].keys()) == {
        "episodic_append_count",
        "episodic_append_event_types",
        "working_memory_new",
    }

    phase_node = trace["nodes"]["phase_classifier"]
    assert set(phase_node["input_summary"].keys()) == {
        "previous_phase",
        "recent_phase_history",
        "recent_turn_count",
        "user_text_excerpt",
    }
    assert set(phase_node["output_summary"].keys()) == {"current_phase"}

    planner_node = trace["nodes"]["planner"]
    assert set(planner_node["input_summary"].keys()) == {
        "current_phase",
        "phase_card_phase",
        "user_text_excerpt",
        "recent_dialogue_count",
        "memory_working",
        "negotiation_state",
        "planner_state",
        "selected_memory_count",
        "selected_memory_ids",
    }
    assert set(planner_node["output_summary"].keys()) == {
        "status",
        "decision",
        "turn_goal",
        "must_include",
        "must_avoid",
        "limits",
        "memory_targets",
        "done_criteria",
    }

    executor_node = trace["nodes"]["executor"]
    assert set(executor_node["input_summary"].keys()) == {
        "current_phase",
        "phase_card_phase",
        "user_text_excerpt",
        "recent_dialogue_count",
        "planner_status",
        "planner_decision",
        "planner_turn_goal",
        "selected_memory_count",
        "selected_memory_ids",
        "response_limits",
    }
    assert set(executor_node["output_summary"].keys()) == {
        "status",
        "spoken_text_excerpt",
        "spoken_text_length",
        "memory_used",
        "refusal_reason",
    }

    trace_str = str(trace)
    assert "planner_prompt" not in trace_str
    assert "task_input" not in trace_str


def test_planner_refuse_status_does_not_create_fake_refusal_reason(monkeypatch):
    session = SessionState(user_id="u_planner_refuse", session_id="s_planner_refuse")
    config = build_negotiation_pipeline_config().model_copy(update={"feature_safety": False, "feature_traces": True})

    def _fake_build_client():
        return object()

    def _fake_refresh_request_context(client, canonical_state, mode_default):
        _ = (client, canonical_state, mode_default)
        return {"conversation": "conv-refuse"}

    def _fake_execute_memory_and_phase(**kwargs):
        _ = kwargs
        mem_call = _fake_model_result(
            {
                "schema_version": "memory.v1",
                "episodic_append": [],
                "working_memory_new": {
                    "current_topic": "precio",
                    "pending_question": None,
                    "last_turn_summary": "mem",
                },
            }
        )
        phase_call = _fake_model_result({"schema_version": "phase_classifier.v1", "current_phase": "propuesta_creativa"})
        return mem_call, 3, phase_call, 4, {"conversation": "conv-refuse"}

    def _fake_call_structured(client, model, messages, response_model, reasoning_effort, request_context, store):
        _ = (client, model, messages, reasoning_effort, request_context, store)
        if response_model.__name__ == "PlannerOutput":
            return _fake_model_result(
                {
                    "schema_version": "planner.v3",
                    "status": "refuse",
                    "turn_goal": "no avanzar",
                    "decision": "reject",
                    "content_plan": {"must_include": [], "must_avoid": []},
                    "limits": {
                        "max_sentences": 2,
                        "max_questions": 0,
                        "allow_topic_shift": False,
                        "allow_personal_disclosure": False,
                    },
                    "memory_targets": [],
                    "done_criteria": ["stop"],
                }
            )
        if response_model.__name__ == "ExecutorOutput":
            return _fake_model_result(
                {
                    "schema_version": "executor.v1",
                    "status": "deliver",
                    "spoken_text": "ok",
                    "memory_used": [],
                    "refusal_reason": None,
                }
            )
        raise AssertionError("unexpected model")

    monkeypatch.setattr(fc, "_build_client", _fake_build_client)
    monkeypatch.setattr(fc, "refresh_request_context", _fake_refresh_request_context)
    monkeypatch.setattr(fc, "_execute_memory_and_phase", _fake_execute_memory_and_phase)
    monkeypatch.setattr(fc, "_call_structured", _fake_call_structured)

    run_negotiation_cognitive_turn(session, "Necesito respuesta", config)

    trace = session.world_state[f"{config.memory_key}_traces"][0]
    assert trace["nodes"]["planner"]["status"] == "refuse"
    assert trace["nodes"]["planner"]["refusal_reason"] is None


