from negotiation.telemetry.live_trace2 import (
    append_livetrace2_event,
    build_livetrace2_event,
    build_semantic_turn_model,
    list_recent_livetrace2_events,
)


class _Session:
    turn_count = 3


def test_livetrace2_semantic_adapter_includes_world_judge_input_when_meta_exists():
    payload = {
        "user_message": "Me interesa el coche",
        "executor_output": {
            "response_text": "Perfecto, ¿qué presupuesto tienes?",
            "asked_question": True,
            "requested_info_slots": ["clarify_context"],
        },
        "semantic_judge": {"schema_version": "judge_semantic_v1", "topic_alignment": "on_topic"},
        "planner_semantic_output": {"schema_version": "planner_semantic_v1", "phase": "clima_humano"},
        "world_judge_meta": {
            "judge_latency_ms": 11,
            "judge_start_ts": "2026-01-01T00:00:00Z",
            "judge_end_ts": "2026-01-01T00:00:00Z",
            "judge_input_prompt_rendered": "[system]\nJudge system prompt\n[user]\nJudge user prompt",
            "judge_output_text_rendered": '{"schema_version":"judge_semantic_v1"}',
        },
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

    node_by_name = {node["node_name"]: node for node in event["nodes"]}
    world_node = node_by_name["world_judge_llm"]
    assert world_node["status"] == "ok"
    assert world_node["input_capture_state"] == "captured"
    assert "Judge system prompt" in world_node["input_prompt_rendered"]


def test_livetrace2_executor_node_uses_final_executor_output_not_raw_llm_text():
    payload = {
        "user_message": "Hola",
        "executor_output": {
            "schema_version": "executor_v2",
            "response_text": "¿Cuál es tu presupuesto?",
            "asked_question": True,
            "requested_info_slots": ["clarify_context"],
            "render_meta": {"word_cap_limit": 30},
        },
        "trace_runtime": {
            "llm_calls": [
                {
                    "name": "executor_llm",
                    "node": "executor",
                    "latency_ms": 19,
                    "output_text_rendered": '{"schema_version":"executor_v2","response_text":"RAW","requested_info_slots":[]}',
                    "output_payload_raw": {"response_text": "RAW", "requested_info_slots": []},
                }
            ]
        },
    }
    event = build_semantic_turn_model(
        user_id="u1",
        session_id="s1",
        turn_count=2,
        trace_index=0,
        payload=payload,
        ts="2026-01-01T00:00:02Z",
    )

    node_by_name = {node["node_name"]: node for node in event["nodes"]}
    executor_node = node_by_name["executor_llm"]
    shown = executor_node["output_payload_parsed"]["final_executor_output"]

    assert shown == payload["executor_output"]
    assert shown["asked_question"] is True
    assert shown["requested_info_slots"]


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


def test_livetrace2_keeps_populated_planner_and_executor_prompts_in_nodes():
    payload = {
        "user_message": "Hola",
        "assistant_message": "Seguimos",
        "semantic_judge": {"schema_version": "judge_semantic_v1"},
        "planner_semantic_output": {"schema_version": "planner_semantic_v1", "phase": "clima_humano"},
        "executor_output": {"schema_version": "executor_v2", "response_text": "Seguimos"},
        "trace_runtime": {
            "llm_calls": [
                {
                    "name": "planner_llm",
                    "node": "phase_policy_planner",
                    "latency_ms": 9,
                    "input_prompt_rendered": "OBJECTIVE_SUMMARY: Objetivo: avanzar.\nFULL_PROFILES_BLOCK: BLOQUE_PERFILES_COMPLETOS\nMEMORY_SHORT: SIN_MEMORIA_CORTA_AUN\nMEMORY_LONG: SIN_RESUMEN_AUN\nPHASE_MAP_JSON: {\"clima_humano\": {\"titulo\": \"Clima humano\"}}",
                    "output_text_rendered": "{}",
                },
                {
                    "name": "executor_llm",
                    "node": "executor",
                    "latency_ms": 11,
                    "input_prompt_rendered": "A) BLOQUE_PERFILES_COMPLETOS\n{\"persona\": {\"persona_id\": \"buyer_mustang67_v1\"}, \"scene\": {\"scene_id\": \"mustang67_in_person_viewing\"}, \"style\": {\"style_id\": \"psyplay_compact\"}}\nL) PHASE_MAP_JSON (opcional)\n{\"clima_humano\": {\"titulo\": \"Clima humano\"}}",
                    "output_text_rendered": "{}",
                },
            ]
        },
    }
    event = build_semantic_turn_model(
        user_id="u1",
        session_id="s1",
        turn_count=2,
        trace_index=0,
        payload=payload,
        ts="2026-01-01T00:00:02Z",
    )

    nodes = {node["node_name"]: node for node in event["nodes"]}
    planner_prompt = str(nodes["planner_llm"].get("input_prompt_rendered") or "")
    executor_prompt = str(nodes["executor_llm"].get("input_prompt_rendered") or "")

    assert "OBJECTIVE_SUMMARY: Objetivo: avanzar." in planner_prompt
    assert "FULL_PROFILES_BLOCK: BLOQUE_PERFILES_COMPLETOS" in planner_prompt
    assert "PHASE_MAP_JSON:" in planner_prompt
    assert "buyer_mustang67_v1" in executor_prompt
    assert "mustang67_in_person_viewing" in executor_prompt
    assert "L) PHASE_MAP_JSON (opcional)" in executor_prompt
