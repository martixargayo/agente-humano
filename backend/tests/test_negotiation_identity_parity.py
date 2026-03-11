from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from api.app import app
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_service import run_negotiation_turn_canonical
from negociacion.state.shared_types import NegotiationChannel, NegotiationExecutionProfile
from sessions.state import SESSIONS, SessionState


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_avatar_experimental_rejected_by_backend_contract():
    client = TestClient(app)
    res = client.post(
        "/api/negotiation/turn",
        json={
            "user_id": "u1",
            "session_id": "s1",
            "message": "hola",
            "channel": "avatar",
            "execution_profile": "experimental_negotiation",
        },
    )
    assert res.status_code == 400
    assert "no permitido" in res.json()["detail"]


def test_backend_chat_and_negotiation_session_namespaces_are_isolated(monkeypatch):
    from api import app as app_mod

    client = TestClient(app)
    SESSIONS.clear()

    # chat path creates chat:: namespace
    chat = client.post("/chat", json={"user_id": "u_sep", "session_id": "same", "message": "hola"})
    assert chat.status_code == 200

    # negotiation path creates neg:: namespace
    def _fake_run(**kwargs):
        state = kwargs["state"]
        return type(
            "R",
            (),
            {
                "reply": "ok",
                "updated_state": state,
                "turn_trace": None,
                "effective_config": {},
                "effective_config_hash": "h",
                "execution_profile": NegotiationExecutionProfile.canonical_negotiation,
                "channel": NegotiationChannel.avatar,
                "prompts_dir_effective": "x",
                "finish_button_armed": False,
            },
        )()

    monkeypatch.setattr(app_mod, "run_negotiation_turn_canonical", _fake_run)

    neg = client.post(
        "/api/negotiation/turn",
        json={
            "user_id": "u_sep",
            "session_id": "same",
            "message": "hola",
            "channel": "avatar",
            "execution_profile": "canonical_negotiation",
        },
    )
    assert neg.status_code == 200

    assert ("u_sep", "chat::same") in SESSIONS
    assert ("u_sep", "neg::same") in SESSIONS
    assert ("u_sep", "same") not in SESSIONS


def test_avatar_and_optimizer_canonical_trace_hashes_match_under_deterministic_time(monkeypatch):
    from negociacion.orchestration import flow_config as flow

    monkeypatch.setattr(flow.uuid, "uuid4", lambda: "turn-fixed")
    monkeypatch.setattr(flow, "datetime", _FixedDateTime)

    config = build_negotiation_pipeline_config().model_copy(update={"feature_traces": True})

    avatar_state = SessionState(user_id="u_same", session_id="s_same")
    optimizer_state = SessionState(user_id="u_same", session_id="s_same")

    avatar_res = run_negotiation_turn_canonical(
        state=avatar_state,
        user_message="hola",
        config=config,
        channel=NegotiationChannel.avatar,
        execution_profile=NegotiationExecutionProfile.canonical_negotiation,
    )
    optimizer_res = run_negotiation_turn_canonical(
        state=optimizer_state,
        user_message="hola",
        config=config,
        channel=NegotiationChannel.optimizer,
        execution_profile=NegotiationExecutionProfile.canonical_negotiation,
    )

    a = avatar_res.turn_trace
    b = optimizer_res.turn_trace

    assert avatar_res.effective_config_hash == optimizer_res.effective_config_hash
    assert a.memory_input_hash == b.memory_input_hash
    assert a.phase_input_hash == b.phase_input_hash
    assert a.planner_input_hash == b.planner_input_hash
    assert a.executor_input_hash == b.executor_input_hash
    assert a.planner_output_hash == b.planner_output_hash
    assert a.executor_output_before_guardrail_hash == b.executor_output_before_guardrail_hash
    assert a.final_reply_text == b.final_reply_text
    assert a.conversation_id_before == b.conversation_id_before
    assert a.conversation_id_after == b.conversation_id_after
    assert a.previous_response_id_before == b.previous_response_id_before
    assert a.previous_response_id_after == b.previous_response_id_after
