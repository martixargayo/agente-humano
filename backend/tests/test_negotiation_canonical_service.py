from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import app
from negociacion.orchestration.turn_service import run_negotiation_turn_canonical
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.state.shared_types import NegotiationChannel, NegotiationExecutionProfile
from sessions.state import SessionState


def test_channel_profile_guard_rejects_avatar_experimental():
    state = SessionState(user_id="u", session_id="s")
    config = build_negotiation_pipeline_config()
    try:
        run_negotiation_turn_canonical(
            state=state,
            user_message="hola",
            config=config,
            channel=NegotiationChannel.avatar,
            execution_profile=NegotiationExecutionProfile.experimental_negotiation,
        )
    except ValueError as exc:
        assert "no permitido" in str(exc)
    else:
        raise AssertionError("Expected ValueError for avatar+experimental")


def test_api_negotiation_turn_returns_canonical_metadata(monkeypatch):
    client = TestClient(app)

    def _fake_run(**kwargs):
        _ = kwargs
        return SimpleNamespace(
            reply="ok",
            updated_state=SessionState(user_id="u", session_id="s"),
            turn_trace=SimpleNamespace(
                conversation_id_before=None,
                previous_response_id_before=None,
                memory_input_hash="m",
                phase_input_hash="ph",
                planner_input_hash="pl_in",
                executor_input_hash="ex_in",
                planner_output_hash="pl_out",
                executor_output_before_guardrail_hash="ex_out",
                final_reply_text="ok",
            ),
            effective_config={"a": 1},
            effective_config_hash="hash123",
            execution_profile=NegotiationExecutionProfile.canonical_negotiation,
            channel=NegotiationChannel.avatar,
            prompts_dir_effective="/tmp/prompts",
            finish_button_armed=True,
        )

    monkeypatch.setattr("api.app.run_negotiation_turn_canonical", _fake_run)

    res = client.post(
        "/api/negotiation/turn",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "message": "hola",
            "channel": "avatar",
            "execution_profile": "canonical_negotiation",
        },
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["reply"] == "ok"
    assert payload["effective_config_hash"] == "hash123"
    assert payload["execution_profile"] == "canonical_negotiation"
    assert payload["channel"] == "avatar"
    assert payload["prompts_dir_effective"] == "/tmp/prompts"
    assert payload["trace_probe"]["planner_output_hash"] == "pl_out"


def test_negociar_is_thin_wrapper_over_canonical(monkeypatch):
    client = TestClient(app)

    def _fake_runner(payload):
        assert payload.channel == "avatar"
        assert payload.execution_profile == "canonical_negotiation"
        return SimpleNamespace(reply="wrap", finish_button_armed=False)

    monkeypatch.setattr("api.app._run_canonical_negotiation", _fake_runner)

    res = client.post("/negociar", json={"user_id": "u1", "session_id": "s1", "message": "hola"})
    assert res.status_code == 200
    assert res.json() == {"reply": "wrap", "finish_button_armed": False}
