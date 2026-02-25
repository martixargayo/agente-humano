from negotiation.telemetry.live_trace2 import (
    append_livetrace2_event,
    build_livetrace2_event,
    build_semantic_turn_model,
    list_recent_livetrace2_events,
)


class _Session:
    turn_count = 3


def test_livetrace2_semantic_adapter_builds_renderable_turn_model():
    payload = {
        "user_message": "Me interesa el coche",
        "executor_output": {
            "response_text": "Perfecto, ¿qué presupuesto tienes?",
            "asked_question": True,
            "requested_info_slots": [],
        },
        "semantic_judge": {"schema_version": "judge_semantic_v1", "topic_alignment": "on_topic"},
        "planner_semantic_output": {"schema_version": "planner_semantic_v1", "phase": "clima_humano"},
        "world_judge_meta": {"judge_latency_ms": 11, "judge_start_ts": "2026-01-01T00:00:00Z", "judge_end_ts": "2026-01-01T00:00:00Z"},
        "planner_meta": {"planner_latency_ms": 14, "planner_start_ts": "2026-01-01T00:00:01Z", "planner_end_ts": "2026-01-01T00:00:01Z"},
    }
    event = build_semantic_turn_model(
        user_id="u1",
        session_id="s1",
        turn_count=2,
        trace_index=0,
        payload=payload,
        ts="2026-01-01T00:00:02Z",
    )

    assert event["user_message"] == "Me interesa el coche"
    assert event["assistant_message"] == "Perfecto, ¿qué presupuesto tienes?"
    node_by_name = {node["node_name"]: node for node in event["nodes"]}
    assert node_by_name["world_judge_llm"]["status"] == "ok"
    assert node_by_name["planner_llm"]["status"] == "ok"
    assert node_by_name["executor_llm"]["status"] == "ok"


def test_livetrace2_buffer_roundtrip_with_renderable_event():
    trace_item = {
        "user_message": "Hola",
        "executor_output": {"response_text": "Seguimos."},
        "semantic_judge": {"schema_version": "judge_semantic_v1"},
        "planner_semantic_output": {"schema_version": "planner_semantic_v1"},
    }
    event = build_livetrace2_event(
        user_id="u1",
        session_id="s1",
        session=_Session(),
        trace_index=0,
        trace_item=trace_item,
    )
    append_livetrace2_event(event)
    recent = list_recent_livetrace2_events(limit=1)
    assert recent
    assert recent[-1]["user_message"] == "Hola"
    assert recent[-1]["assistant_message"] == "Seguimos."
    assert isinstance(recent[-1].get("nodes"), list)


def test_livetrace2_generator_emits_renderable_trace2_after_connected():
    from app import _livetrace2_sse_generator

    append_livetrace2_event(
        {
            "user_id": "u1",
            "session_id": "s1",
            "trace_index": 1,
            "turn_idx": 1,
            "user_message": "Hola",
            "assistant_message": "¿Qué presupuesto tienes?",
            "nodes": [{"node_name": "executor_llm", "status": "ok", "node_type": "llm"}],
        }
    )

    gen = _livetrace2_sse_generator()
    first = next(gen)
    second = next(gen)
    assert first == ": connected\n\n"
    assert "event: trace2" in second
    assert '"user_message": "Hola"' in second
