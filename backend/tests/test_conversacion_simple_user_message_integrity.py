from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from conversacion_simple.orchestration.pipeline import StructuredBrainCall
from interfaz_usuario import services as iu_services
from negociacion.optimizador import services as opt_services
from sessions.state import get_session_state, get_session_store


def _fake_brain_output(reply_text: str = "ok") -> dict:
    return {
        "schema_version": "brain.v1",
        "status": "deliver",
        "assistant_response": {"text": reply_text},
        "state_patch": {
            "conversation_state": {"phase": "desarrollo", "status": "active", "current_turn_goal": "avanzar"},
            "memory_working": {"current_topic": "tema", "pending_question": None, "last_turn_summary": "resumen"},
            "memory_episodic_append": [{"event_type": "important_fact", "event_summary": "fact", "turn_id": "t1"}],
        },
    }


def _install_fake_brain(monkeypatch, reply_text: str = "ok") -> None:
    def _fake_call(**kwargs):
        return StructuredBrainCall(source="model", parsed_json=_fake_brain_output(reply_text), response=None)

    monkeypatch.setattr("conversacion_simple.orchestration.pipeline._call_brain_structured", _fake_call)


def _install_optimizer_noop_overrides(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.apply_overrides", lambda base_config, entries, context_id=None: (base_config, None))
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1})


def test_optimizador_conversacion_simple_dialogue_keeps_user_text(monkeypatch) -> None:
    get_session_store().clear()
    _install_fake_brain(monkeypatch, reply_text="respuesta-cs")
    _install_optimizer_noop_overrides(monkeypatch)

    opt_services.ensure_session(user_id="u_opt", session_id="s_opt", flow_id="conversacion_simple", context_id="baseline")
    state_before = get_session_state(user_id="u_opt", session_id="s_opt")
    state_before.world_state["negotiation_canonical_traces"] = [
        {"turn_id": "legacy-neg", "user_turn": {"raw_text": ""}, "final_reply_text": "legacy"}
    ]
    out = opt_services.run_sandbox_turn(
        optimizer_session_id="opt",
        user_id="u_opt",
        session_id="s_opt",
        message="hola desde optimizador",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    assert out["reply"] == "respuesta-cs"
    dialogue = opt_services.get_dialogue("u_opt", "s_opt")
    assert len(dialogue) == 2
    assert dialogue[-2]["role"] == "user"
    assert dialogue[-2]["text"] == "hola desde optimizador"

    state = get_session_state(user_id="u_opt", session_id="s_opt")
    trace = state.world_state["conversation_simple_canonical_traces"][-1]
    assert trace["user_turn"]["raw_text"] == "hola desde optimizador"


def test_optimizador_conversacion_simple_multi_turn_dialogue_persists_user_text(monkeypatch) -> None:
    get_session_store().clear()
    _install_fake_brain(monkeypatch, reply_text="ok")
    _install_optimizer_noop_overrides(monkeypatch)

    opt_services.ensure_session(user_id="u_opt2", session_id="s_opt2", flow_id="conversacion_simple", context_id="baseline")

    for msg in ["primer turno", "segundo turno"]:
        opt_services.run_sandbox_turn(
            optimizer_session_id="opt",
            user_id="u_opt2",
            session_id="s_opt2",
            message=msg,
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )

    dialogue = opt_services.get_dialogue("u_opt2", "s_opt2")
    user_messages = [item["text"] for item in dialogue if item["role"] == "user"]
    assert user_messages == ["primer turno", "segundo turno"]


def test_interfaz_usuario_conversacion_simple_turn_preserves_user_text(monkeypatch) -> None:
    get_session_store().clear()
    _install_fake_brain(monkeypatch, reply_text="respuesta-ui")

    iu_services.ensure_session(user_id="u_ui", session_id="s_ui", context_id="baseline")
    out = iu_services.run_turn(user_id="u_ui", session_id="s_ui", message="hola desde interfaz", new_conversation=False)

    assert out["reply"] == "respuesta-ui"
    state = get_session_state(user_id="u_ui", session_id="s_ui")
    assert state.history[-2]["role"] == "user"
    assert state.history[-2]["content"] == "hola desde interfaz"
    trace = state.world_state["conversation_simple_canonical_traces"][-1]
    assert trace["user_turn"]["raw_text"] == "hola desde interfaz"


def test_surface_paths_share_runtime_but_optimizer_adds_overrides_layer(monkeypatch) -> None:
    get_session_store().clear()
    _install_fake_brain(monkeypatch, reply_text="ok")

    counters = {"optimizer_apply_overrides": 0}

    def _wrapped_apply_overrides(base_config, entries, context_id=None):
        counters["optimizer_apply_overrides"] += 1
        return base_config, None

    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.apply_overrides", _wrapped_apply_overrides)
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1})

    opt_services.ensure_session(user_id="u_cmp", session_id="s_cmp_opt", flow_id="conversacion_simple", context_id="baseline")
    opt_services.run_sandbox_turn(
        optimizer_session_id="opt-cmp",
        user_id="u_cmp",
        session_id="s_cmp_opt",
        message="hola optimizer",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )
    assert counters["optimizer_apply_overrides"] == 1

    iu_services.ensure_session(user_id="u_cmp", session_id="s_cmp_ui", context_id="baseline")
    iu_services.run_turn(user_id="u_cmp", session_id="s_cmp_ui", message="hola ui", new_conversation=False)
    assert counters["optimizer_apply_overrides"] == 1
