from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interfaz_usuario import services as iu_services
from negociacion.optimizador import services as opt_services
from negociacion.optimizador import trace_reader
from sessions.state import SessionState, get_session_state, get_session_store


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    get_session_store().clear()


def test_interfaz_usuario_bootstrap_conversacion_simple_context() -> None:
    payload = iu_services.ensure_session(user_id="u_cs", session_id="s_cs", context_id="baseline")

    assert payload["context_id"] == "baseline"
    state = get_session_state(user_id="u_cs", session_id="s_cs")
    assert state.world_state["conversacion_simple_context"]["flow_id"] == "conversacion_simple"


def test_interfaz_usuario_turn_routes_to_conversacion_simple(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_cs", session_id="s_cs", context_id="baseline")

    called = {"cs": 0, "neg": 0}

    def _fake_cs_turn(*, state, user_message, config, turn_context, **kwargs):
        called["cs"] += 1
        canonical = state.world_state.setdefault(
            config.memory_key,
            {
                "ui_state": {"finish_button_armed": True},
            },
        )
        canonical.setdefault("ui_state", {})["finish_button_armed"] = True
        return "respuesta cs", state, {"turn_id": "turn-cs"}

    def _fake_neg(*args, **kwargs):
        called["neg"] += 1
        return "respuesta neg", None, {"entry_contract": {}, "trace_count": 0}

    monkeypatch.setattr("interfaz_usuario.services.run_conversacion_simple_turn", _fake_cs_turn)
    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _fake_neg)

    out = iu_services.run_turn(user_id="u_cs", session_id="s_cs", message="hola")

    assert out["reply"] == "respuesta cs"
    assert out["finish_button_armed"] is True
    assert called == {"cs": 1, "neg": 0}


def test_interfaz_usuario_finalize_conversacion_simple() -> None:
    iu_services.ensure_session(user_id="u_cs", session_id="s_cs", context_id="baseline")
    out = iu_services.finalize_session(user_id="u_cs", session_id="s_cs")
    assert out["status"] == "finalized"


def test_interfaz_usuario_context_conflict_cross_flow() -> None:
    iu_services.ensure_session(user_id="u_conf", session_id="s_conf", context_id="baseline")
    with pytest.raises(Exception):
        iu_services.ensure_session(user_id="u_conf", session_id="s_conf", context_id="baseline_current")


def test_interfaz_usuario_negociacion_regression_path(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_neg", session_id="s_neg", context_id="baseline_current")
    called = {"neg": 0}

    def _fake_neg(*args, **kwargs):
        called["neg"] += 1
        state = kwargs["state"]
        return "ok-neg", state, {
            "entry_contract": {
                "entry_surface": "interfaz_usuario",
                "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                "overrides_applied": False,
                "optimizer_wrapper_used": False,
                "new_conversation": False,
                "clone_used": False,
                "config_snapshot": {
                    "memory_key": "negotiation_canonical",
                    "thread_mode_default": "conversation",
                    "model_memory": "m",
                    "model_phase_classifier": "m",
                    "model_planner": "m",
                    "model_executor": "m",
                    "max_recent_messages": 12,
                    "max_executor_recent_turns": 8,
                },
            },
            "trace_count": 1,
        }

    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _fake_neg)

    out = iu_services.run_turn(user_id="u_neg", session_id="s_neg", message="hola")
    assert out["reply"] == "ok-neg"
    assert called["neg"] == 1


def test_optimizador_list_contexts_includes_conversacion_simple() -> None:
    items = opt_services.list_contexts()
    context_ids = {item["context_id"] for item in items}
    assert "baseline" in context_ids
    assert "negociacion_sala_reuniones" in context_ids


def test_optimizador_list_prompts_for_conversacion_simple_session() -> None:
    opt_services.ensure_session(user_id="u_opt", session_id="s_opt", context_id="baseline")
    prompts = opt_services.list_prompts(user_id="u_opt", session_id="s_opt")
    assert [item["node"] for item in prompts] == ["brain"]


def test_optimizador_sandbox_turn_routes_to_conversacion_simple(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_opt", session_id="s_opt", context_id="baseline")
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.apply_overrides", lambda base_config, entries, context_id=None, flow_id=None: (base_config, None))
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1})

    out = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-1",
        user_id="u_opt",
        session_id="s_opt",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    assert isinstance(out["reply"], str) and out["reply"]
    assert out["comparable_to_interfaz_usuario_base"] is True
    assert out["comparability_reason"] == "no_overrides"


def test_conversacion_simple_rejects_prompt_overrides_explicitly(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_parity", session_id="s_opt", flow_id="conversacion_simple", context_id="baseline")

    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.resolve_entries",
        lambda **_: [{"category": "prompt", "key": "brain", "value": "legacy override"}],
    )
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.describe_effective_overrides",
        lambda entries: {"prompt": {"brain": "legacy override"}, "config": {}, "contextual": {}},
    )
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.get_state",
        lambda optimizer_session_id: {"mode": "sandbox", "workspace_version": 2},
    )

    with pytest.raises(Exception) as excinfo:
        opt_services.run_sandbox_turn(
            optimizer_session_id="opt-parity",
            user_id="u_parity",
            session_id="s_opt",
            message="hola",
            conversation_id=None,
            scope_turn_id=None,
            repeat_from_turn_id=None,
        )
    detail = getattr(excinfo.value, "detail", {})
    assert isinstance(detail, dict)
    assert detail.get("error") == "conversacion_simple_prompt_override_not_supported"


def test_trace_reader_supports_single_brain_node() -> None:
    state = SessionState(user_id="u_t", session_id="s_t")
    state.world_state["conversation_simple_canonical_traces"] = [
        {
            "turn_id": "t1",
            "final_status": "clarify",
            "timestamp_utc": "2026-01-01T00:00:00+00:00",
            "nodes": {"brain": {"model_called": False, "status": "clarify", "latency_ms": 1}},
            "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline", "context_version": "1.0.0"}},
        }
    ]
    state.world_state["_session_surface"] = "optimizador"
    get_session_store().save(state)

    turns = trace_reader.list_turns(user_id="u_t", session_id="s_t")
    assert turns[0]["flow_id"] == "conversacion_simple"
    assert turns[0]["fallback_used"] is True


def test_optimizador_marks_non_comparable_when_conversacion_simple_has_overrides(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_cmp", session_id="s_cmp", flow_id="conversacion_simple", context_id="baseline")

    def _fake_cs_turn(*, state, user_message, config, turn_context, **kwargs):
        state.world_state.setdefault("conversation_simple_canonical_traces", []).append(
            {
                "turn_id": "turn-cmp",
                "final_status": "deliver",
                "nodes": {"brain": {"model_called": True, "status": "deliver", "latency_ms": 5}},
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
            }
        )
        return "ok-cmp", state, {"turn_id": "turn-cmp"}

    monkeypatch.setattr("negociacion.optimizador.services.run_conversacion_simple_turn", _fake_cs_turn)
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.resolve_entries",
        lambda **_: [{"category": "config", "key": "maintenance_retry_limit", "value": 5, "scope": "this_optimizer_session"}],
    )
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.apply_overrides",
        lambda base_config, entries, context_id=None, flow_id=None: (base_config.model_copy(update={"maintenance_retry_limit": 5}), None),
    )
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {"maintenance_retry_limit": {"value": 5}}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "sandbox", "workspace_version": 2})

    out = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-cmp",
        user_id="u_cmp",
        session_id="s_cmp",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )
    assert out["comparable_to_interfaz_usuario_base"] is False
    assert out["comparability_reason"] == "overrides_applied"


def test_compare_turns_cross_flow_fails_controlled() -> None:
    state = SessionState(user_id="u_cmp", session_id="s_cmp")
    state.world_state["negotiation_canonical_traces"] = [
        {"turn_id": "a", "_optimizador": {"base_context": {"flow_id": "negociacion", "context_id": "baseline_current"}}},
        {"turn_id": "b", "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline"}}},
    ]
    state.world_state["_session_surface"] = "optimizador"
    get_session_store().save(state)

    with pytest.raises(ValueError, match="cross_flow_compare_not_supported"):
        opt_services.compare_turns("a", "b")
