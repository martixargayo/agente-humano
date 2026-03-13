from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import app
from negociacion.optimizador import experiments_bridge
from negociacion.optimizador.storage import resolve_traces
from sessions.state import SESSIONS, SessionState, get_session_state

client = TestClient(app)


def _append_fake_negotiation_trace(state: SessionState, user_message: str, _config: Any) -> tuple[str, SessionState]:
    memory_key = "negotiation_canonical"
    traces_key = f"{memory_key}_traces"
    traces = state.world_state.setdefault(traces_key, [])
    if not isinstance(traces, list):
        traces = []
        state.world_state[traces_key] = traces

    before_conv = None
    before_prev = None
    if traces:
        latest = traces[-1] if isinstance(traces[-1], dict) else {}
        before_conv = latest.get("conversation_id_after")
        before_prev = latest.get("previous_response_id_after")

    idx = len(traces) + 1
    after_conv = before_conv or f"conv-{state.user_id}-{state.session_id}"
    after_prev = f"resp-{idx}"
    traces.append(
        {
            "turn_id": f"turn-{idx}",
            "final_status": "ok",
            "final_reply_text": f"stub-reply::{user_message}",
            "conversation_id_before": before_conv,
            "conversation_id_after": after_conv,
            "previous_response_id_before": before_prev,
            "previous_response_id_after": after_prev,
        }
    )

    canonical = state.world_state.setdefault(memory_key, {})
    if isinstance(canonical, dict):
        thread = canonical.setdefault("openai_thread", {})
        if isinstance(thread, dict):
            thread["conversation_id"] = after_conv
            thread["previous_response_id"] = after_prev

    return f"stub-reply::{user_message}", state


def _clone_equivalent_session(*, source_user_id: str, source_session_id: str, dest_user_id: str, dest_session_id: str) -> None:
    source = get_session_state(user_id=source_user_id, session_id=source_session_id)
    cloned = copy.deepcopy(source)
    cloned.user_id = dest_user_id
    cloned.session_id = dest_session_id
    SESSIONS[(dest_user_id, dest_session_id)] = cloned


def _seed_neutral_base_state(*, user_id: str, session_id: str) -> SessionState:
    state = get_session_state(user_id=user_id, session_id=session_id)
    state.world_state.setdefault("parity_seed", {"seeded_by": "test_helper", "version": 1})
    return state


@pytest.fixture(autouse=True)
def _clean_state_and_stub_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    SESSIONS.clear()
    experiments_bridge._OVERRIDE_STORE.clear()
    monkeypatch.setattr(
        "negociacion.orchestration.turn_contract.run_negotiation_cognitive_turn",
        _append_fake_negotiation_trace,
    )
    monkeypatch.setattr("api.app.run_agent", lambda _state, _msg: ("chat-stub", _state))


def test_interfaz_usuario_surface_is_detached_from_avatar_legacy_endpoints() -> None:
    app_js = "backend/interfaz_usuario_app/app.js"
    content = open(app_js, "r", encoding="utf-8").read()
    assert "/api/interfaz_usuario" in content
    assert "'/chat'" not in content
    assert '"/chat"' not in content
    assert "'/negociar'" not in content
    assert '"/negociar"' not in content




def test_interfaz_usuario_runtime_does_not_depend_on_legacy_chat_or_negociar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("api.app.run_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy /chat should not be used")))
    monkeypatch.setattr("api.app.run_negotiation_agent", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy /negociar should not be used")))

    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_detached", "session_id": "s_detached", "message": "hola", "new_conversation": False},
    )
    assert turn.status_code == 200
    assert turn.json()["entry_contract"]["entry_surface"] == "interfaz_usuario"


def test_interfaz_usuario_turn_wires_shared_contract_into_trace() -> None:
    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_iu", "session_id": "s_iu", "message": "Hola", "new_conversation": False},
    )
    assert turn.status_code == 200
    body = turn.json()

    assert body["entry_contract"]["entry_surface"] == "interfaz_usuario"
    assert body["entry_contract"]["entrypoint"] == "/api/interfaz_usuario/negociacion/turn"
    assert body["entry_contract"]["overrides_applied"] is False
    assert body["entry_contract"]["optimizer_wrapper_used"] is False
    assert body["latest_turn_id"] == "turn-1"

    traces = resolve_traces(SESSIONS[("u_iu", "s_iu")])
    assert traces[-1]["_entry_contract"]["entry_surface"] == "interfaz_usuario"
    assert traces[-1].get("_optimizador") is None


def test_interfaz_usuario_override_isolation_and_no_chat_leakage() -> None:
    experiments_bridge.update_state(
        "default",
        {
            "mode": "sandbox",
            "entries": [{"category": "config", "key": "max_recent_messages", "value": 3, "scope": "this_optimizer_session"}],
        },
    )

    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_iso", "session_id": "s_iso", "message": "turno interfaz", "new_conversation": False},
    )
    assert turn.status_code == 200
    body = turn.json()
    assert body["entry_contract"]["overrides_applied"] is False

    traces_before_chat = len(resolve_traces(SESSIONS[("u_iso", "s_iso")]))
    r_chat = client.post("/chat", json={"user_id": "u_iso", "session_id": "s_iso", "message": "hola chat"})
    assert r_chat.status_code == 200
    traces_after_chat = len(resolve_traces(SESSIONS[("u_iso", "s_iso")]))
    assert traces_before_chat == traces_after_chat


def test_clean_parity_ab_uses_equivalent_seed_on_separate_sessions() -> None:
    seed_user, seed_session = "u_seed", "s_seed"
    message = "Mismo mensaje controlado"

    # Semilla base neutral interna (sin pasar por superficies HTTP).
    _seed_neutral_base_state(user_id=seed_user, session_id=seed_session)

    _clone_equivalent_session(source_user_id=seed_user, source_session_id=seed_session, dest_user_id="u_opt", dest_session_id="s_opt")
    _clone_equivalent_session(source_user_id=seed_user, source_session_id=seed_session, dest_user_id="u_iu", dest_session_id="s_iu")

    r_optimizer = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "fresh",
            "user_id": "u_opt",
            "session_id": "s_opt",
            "message": message,
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    assert r_optimizer.status_code == 200
    assert r_optimizer.json()["effective_overrides"] == {"prompt": {}, "config": {}, "contextual": {}}

    r_interfaz = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_iu", "session_id": "s_iu", "message": message, "new_conversation": False},
    )
    assert r_interfaz.status_code == 200

    opt_trace = resolve_traces(SESSIONS[("u_opt", "s_opt")])[-1]
    iu_trace = resolve_traces(SESSIONS[("u_iu", "s_iu")])[-1]

    assert opt_trace["final_status"] == iu_trace["final_status"] == "ok"
    assert opt_trace["_entry_contract"]["config_snapshot"] == iu_trace["_entry_contract"]["config_snapshot"]
    assert opt_trace["_entry_contract"]["entry_surface"] == "optimizador"
    assert iu_trace["_entry_contract"]["entry_surface"] == "interfaz_usuario"
    assert opt_trace["_entry_contract"]["overrides_applied"] is False
    assert iu_trace["_entry_contract"]["overrides_applied"] is False


def test_interfaz_new_conversation_creates_clean_session_and_contract_flag() -> None:
    first = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_new", "session_id": "s_new", "message": "primer turno", "new_conversation": False},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_new", "session_id": "s_new", "message": "nuevo hilo", "new_conversation": True},
    )
    assert second.status_code == 200

    body = second.json()
    new_session_id = body["session_id"]
    assert new_session_id != "s_new"
    assert body["entry_contract"]["new_conversation"] is True
    assert len(resolve_traces(SESSIONS[("u_new", new_session_id)])) == 1


def test_optimizer_contract_flags_for_clone_and_new_conversation_paths() -> None:
    user_id, source_session = "u_clone", "s_clone"
    _seed_neutral_base_state(user_id=user_id, session_id=source_session)

    clone_resp = client.post(
        "/api/optimizador/sandbox/clone",
        json={
            "optimizer_session_id": "default",
            "source_user_id": user_id,
            "source_session_id": source_session,
            "source_conversation_id": None,
        },
    )
    assert clone_resp.status_code == 200
    clone_session = clone_resp.json()["session_id"]

    clone_turn = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "default",
            "user_id": user_id,
            "session_id": clone_session,
            "message": "turn clone",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    assert clone_turn.status_code == 200
    assert clone_turn.json()["entry_contract"]["clone_used"] is True
    assert clone_turn.json()["entry_contract"]["new_conversation"] is False

    new_conv_resp = client.post(
        "/api/optimizador/sandbox/new_conversation",
        json={"optimizer_session_id": "default", "user_id": user_id, "session_id": source_session},
    )
    assert new_conv_resp.status_code == 200
    new_conv_session = new_conv_resp.json()["session_id"]

    new_conv_turn = client.post(
        "/api/optimizador/sandbox/turn",
        json={
            "optimizer_session_id": "default",
            "user_id": user_id,
            "session_id": new_conv_session,
            "message": "turn new conv",
            "conversation_id": None,
            "scope_turn_id": None,
            "repeat_from_turn_id": None,
        },
    )
    assert new_conv_turn.status_code == 200
    assert new_conv_turn.json()["entry_contract"]["clone_used"] is False
    assert new_conv_turn.json()["entry_contract"]["new_conversation"] is True


def test_interfaz_auto_resets_on_fresh_opener_after_terminal_phase():
    state = get_session_state(user_id="u_auto", session_id="s_auto")
    state.world_state["negotiation_canonical"] = {
        "planner_state": {"current_phase": "formalizacion_del_acuerdo"},
        "openai_thread": {},
    }
    state.world_state["negotiation_canonical_recent_dialogue"] = [
        {"role": "user", "text": "acepto"},
        {"role": "assistant", "text": "cerramos"},
        {"role": "user", "text": "ok"},
        {"role": "assistant", "text": "firma"},
    ]

    turn = client.post(
        "/api/interfaz_usuario/negociacion/turn",
        json={"user_id": "u_auto", "session_id": "s_auto", "message": "hola, vengo por el coche", "new_conversation": False},
    )

    assert turn.status_code == 200
    body = turn.json()
    assert body["auto_reset_applied"] is True
    assert body["session_id"] != "s_auto"
