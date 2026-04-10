from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app
from conversacion_simple.orchestration import pipeline as cs_pipeline
from sessions.state import get_session_state, reset_session_store


def _fake_brain_call(*, client, model, messages, max_output_tokens=None):
    _ = (client, model, messages, max_output_tokens)
    return cs_pipeline.StructuredBrainCall(
        source="model",
        parsed_json={
            "schema_version": "brain.v1",
            "status": "deliver",
            "assistant_response": {"text": "ok"},
            "state_patch": {
                "conversation_state": {
                    "phase": "avance",
                    "status": "active",
                    "current_turn_goal": "responder",
                    "closure_readiness": "not_ready",
                },
                "memory_working": {
                    "current_topic": "x",
                    "pending_question": None,
                    "last_turn_summary": "y",
                },
                "memory_episodic_append": [],
            },
        },
        response=object(),
        response_id="resp_test",
        schema_observability={"schema_name": "BrainOutput", "validation": {"valid": True}, "openai_subset_validation": {"valid": True}},
        model_attempted=True,
        model_succeeded=True,
        timings_ms={
            "schema_prepare": 0.4,
            "provider_responses_create": 1.2,
            "extract_output_text": 0.1,
            "json_loads": 0.1,
            "total": 1.8,
        },
    )


def test_latency_breakdown_is_exposed_and_structured(monkeypatch):
    reset_session_store()
    monkeypatch.setattr(cs_pipeline, "_call_brain_structured", _fake_brain_call)
    client = TestClient(app)

    boot = client.post(
        "/api/interfaz_usuario/sessions/bootstrap",
        json={"user_id": "u_lat", "session_id": "s_lat", "context_id": "negociacion_sala_reuniones"},
    )
    assert boot.status_code == 200

    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_lat", "session_id": "s_lat", "message": "hola", "new_conversation": False},
    )
    assert turn.status_code == 200
    payload = turn.json()

    breakdown = payload.get("latency_breakdown_ms")
    assert isinstance(breakdown, dict)

    surface = breakdown.get("surface_stage_timings_ms")
    pipeline = breakdown.get("pipeline_stage_timings_ms")
    assert isinstance(surface, dict)
    assert isinstance(pipeline, dict)

    assert "run_conversacion_simple_turn" in surface
    assert "build_conversacion_simple_pipeline_config" in surface
    assert "build_conversacion_simple_turn_context" in surface

    assert "validate_turn_context" in pipeline
    assert "build_brain_input" in pipeline
    assert "build_brain_messages" in pipeline
    assert "parse_and_validate_brain_output" in pipeline
    assert "apply_brain_output_to_state" in pipeline
    assert "save_session_state" in pipeline
    assert "turn_total" in pipeline

    assert breakdown.get("surface_total_ms", 0) >= surface.get("run_conversacion_simple_turn", 0)

    state = get_session_state(user_id="u_lat", session_id="s_lat")
    traces = state.world_state.get("conversation_simple_canonical_traces", [])
    assert isinstance(traces, list) and traces
    latest = traces[-1]
    assert isinstance(latest, dict)
    stage_timings = latest.get("stage_timings_ms")
    assert isinstance(stage_timings, dict)
    assert "brain_call" in stage_timings


def test_frontend_marks_present_and_text_render_before_tts():
    src = open("backend/interfaz_usuario_app/app.js", "r", encoding="utf-8").read()

    required_markers = [
        "send_clicked",
        "request_started",
        "response_body_parsed",
        "reply_render_started",
        "reply_render_finished",
        "tts_request_started",
        "tts_audio_ready",
        "tts_play_started",
        "tts_play_finished",
        "stt_request_started",
        "stt_response_received",
    ]
    for marker in required_markers:
        assert marker in src

    render_idx = src.index("updateReplyText(out.reply || '')")
    tts_idx = src.index("await playTtsWithAvatar(out.reply)")
    assert render_idx < tts_idx
