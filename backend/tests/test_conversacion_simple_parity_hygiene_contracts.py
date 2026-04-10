from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interfaz_usuario import services as iu_services
from negociacion.optimizador import services as opt_services
from sessions.state import get_session_state, get_session_store


@pytest.fixture(autouse=True)
def _clean_store() -> None:
    get_session_store().clear()


def _patch_optimizer_overrides(monkeypatch) -> None:
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.apply_overrides",
        lambda base_config, entries, context_id=None, flow_id=None: (base_config, None),
    )
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.describe_effective_overrides",
        lambda entries: {"prompt": {}, "config": {}, "contextual": {}},
    )
    monkeypatch.setattr(
        "negociacion.optimizador.services.experiments_bridge.get_state",
        lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1},
    )


def test_interfaz_usuario_cs_ignores_negotiation_residue_for_auto_reset(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_cs", session_id="s_cs", context_id="baseline")
    state = get_session_state(user_id="u_cs", session_id="s_cs")
    state.world_state["negotiation_canonical"] = {"planner_state": {"current_phase": "formalizacion_del_acuerdo"}}
    state.world_state["negotiation_canonical_recent_dialogue"] = [{"role": "user", "text": "x"}] * 4

    monkeypatch.setattr(
        "interfaz_usuario.services.run_conversacion_simple_turn",
        lambda *, state, user_message, config, turn_context, **kwargs: ("ok", state, {"turn_id": "turn-cs"}),
    )

    out = iu_services.run_turn(user_id="u_cs", session_id="s_cs", message="hola", new_conversation=False)

    assert out["reply"] == "ok"
    assert out["auto_reset_applied"] is False
    assert out["session_id"] == "s_cs"


def test_interfaz_usuario_cs_does_not_read_finish_button_from_negotiation_ui_state(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_finish", session_id="s_finish", context_id="baseline")
    state = get_session_state(user_id="u_finish", session_id="s_finish")
    state.world_state["negotiation_canonical"] = {"ui_state": {"finish_button_armed": True}}

    monkeypatch.setattr(
        "interfaz_usuario.services.run_conversacion_simple_turn",
        lambda *, state, user_message, config, turn_context, **kwargs: ("ok", state, {"turn_id": "turn-finish"}),
    )

    out = iu_services.run_turn(user_id="u_finish", session_id="s_finish", message="hola", new_conversation=False)

    assert out["finish_button_armed"] is False


def test_interfaz_usuario_cs_reads_finish_button_from_cs_canonical_even_with_negotiation_residue(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_finish_cs", session_id="s_finish_cs", context_id="baseline")
    state = get_session_state(user_id="u_finish_cs", session_id="s_finish_cs")
    state.world_state["negotiation_canonical"] = {"ui_state": {"finish_button_armed": False}}
    state.world_state["conversation_simple_canonical"] = {"ui_state": {"finish_button_armed": True}}

    monkeypatch.setattr(
        "interfaz_usuario.services.run_conversacion_simple_turn",
        lambda *, state, user_message, config, turn_context, **kwargs: ("ok", state, {"turn_id": "turn-finish-cs"}),
    )

    out = iu_services.run_turn(user_id="u_finish_cs", session_id="s_finish_cs", message="hola", new_conversation=False)

    assert out["finish_button_armed"] is True


def test_interfaz_usuario_rejects_mixed_flow_bindings() -> None:
    iu_services.ensure_session(user_id="u_mixed", session_id="s_mixed", context_id="baseline")
    state = get_session_state(user_id="u_mixed", session_id="s_mixed")
    state.world_state["negotiation_context"] = {
        "flow_id": "negociacion",
        "context_id": "baseline_current",
        "context_version": "1.0.0",
    }

    with pytest.raises(HTTPException) as excinfo:
        iu_services.run_turn(user_id="u_mixed", session_id="s_mixed", message="hola", new_conversation=False)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["error"] == "session_has_mixed_flow_bindings"


def test_interfaz_usuario_negociacion_path_still_reads_negotiation_finish_button(monkeypatch) -> None:
    iu_services.ensure_session(user_id="u_neg_finish", session_id="s_neg_finish", context_id="baseline_current")
    state = get_session_state(user_id="u_neg_finish", session_id="s_neg_finish")
    state.world_state["negotiation_canonical"] = {"ui_state": {"finish_button_armed": True}}
    state.world_state["conversation_simple_canonical"] = {"ui_state": {"finish_button_armed": False}}

    def _fake_neg_turn(*args, **kwargs):
        return "ok-neg", kwargs["state"], {"entry_contract": {}, "trace_count": 1, "latest_turn_id": "neg-t1"}

    monkeypatch.setattr("interfaz_usuario.services.execute_turn_with_contract", _fake_neg_turn)

    out = iu_services.run_turn(user_id="u_neg_finish", session_id="s_neg_finish", message="hola", new_conversation=False)
    assert out["finish_button_armed"] is True


def test_optimizer_cs_base_context_metadata_is_flow_aware_and_strict_comparable(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_opt", session_id="s_opt", flow_id="conversacion_simple", context_id="baseline")
    _patch_optimizer_overrides(monkeypatch)

    out = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-1",
        user_id="u_opt",
        session_id="s_opt",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    state = get_session_state(user_id="u_opt", session_id="s_opt")
    trace = state.world_state["conversation_simple_canonical_traces"][-1]
    optimizer_meta = trace.get("_optimizador", {})
    base_context = optimizer_meta.get("base_context", {})

    assert base_context.get("flow_id") == "conversacion_simple"
    assert base_context.get("context_id") == "baseline"
    assert out["comparable_to_interfaz_usuario_base"] is True
    assert out["strict_comparable_to_interfaz_usuario_base"] is True
    assert out["strict_comparability_reason"] == "parity_proxy_ready"


def test_optimizer_cs_strict_comparability_blocks_clone_strategy_even_without_overrides(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_clone", session_id="s_clone", flow_id="conversacion_simple", context_id="baseline")
    state = get_session_state(user_id="u_clone", session_id="s_clone")
    state.world_state["optimizador_sandbox_meta"] = {"clone_strategy": "full_session_with_preferred_conversation"}
    _patch_optimizer_overrides(monkeypatch)

    out = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-2",
        user_id="u_clone",
        session_id="s_clone",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    assert out["comparable_to_interfaz_usuario_base"] is True
    assert out["strict_comparable_to_interfaz_usuario_base"] is False
    assert out["strict_comparability_reason"] == "sandbox_clone_strategy_non_equivalent"


def test_optimizer_cs_multi_turn_no_overrides_keeps_strict_comparability(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_multi", session_id="s_multi", flow_id="conversacion_simple", context_id="baseline")
    _patch_optimizer_overrides(monkeypatch)

    first = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-multi",
        user_id="u_multi",
        session_id="s_multi",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )
    second = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-multi",
        user_id="u_multi",
        session_id="s_multi",
        message="seguimos",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    assert first["strict_comparable_to_interfaz_usuario_base"] is True
    assert second["strict_comparable_to_interfaz_usuario_base"] is True
    assert first["strict_comparability_reason"] == "parity_proxy_ready"
    assert second["strict_comparability_reason"] == "parity_proxy_ready"


def test_optimizer_cs_latch_trace_fields_do_not_break_strict_comparability(monkeypatch) -> None:
    opt_services.ensure_session(user_id="u_latch", session_id="s_latch", flow_id="conversacion_simple", context_id="baseline")
    _patch_optimizer_overrides(monkeypatch)

    call_count = {"n": 0}

    def _fake_cs_turn(*, state, user_message, config, turn_context, **kwargs):
        call_count["n"] += 1
        canonical = state.world_state.setdefault(config.memory_key, {"ui_state": {"finish_button_armed": False}})
        if call_count["n"] == 1:
            canonical.setdefault("ui_state", {})["finish_button_armed"] = True
            closure = "ready"
            latched = False
        else:
            canonical.setdefault("ui_state", {})["finish_button_armed"] = True
            closure = "not_ready"
            latched = True
        state.world_state.setdefault(config.traces_key, []).append(
            {
                "turn_id": f"t{call_count['n']}",
                "timestamp_utc": "2026-01-01T00:00:00+00:00",
                "final_status": "deliver",
                "final_reply_text": "ok",
                "closure_readiness": closure,
                "finish_button_armed": True,
                "finish_button_latched": latched,
                "nodes": {"brain": {"model_called": True, "status": "deliver", "latency_ms": 1}},
            }
        )
        return "ok", state, {"turn_id": f"t{call_count['n']}"}

    monkeypatch.setattr("negociacion.optimizador.services.run_conversacion_simple_turn", _fake_cs_turn)

    first = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-latch",
        user_id="u_latch",
        session_id="s_latch",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )
    second = opt_services.run_sandbox_turn(
        optimizer_session_id="opt-latch",
        user_id="u_latch",
        session_id="s_latch",
        message="gracias",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )

    assert first["strict_comparable_to_interfaz_usuario_base"] is True
    assert second["strict_comparable_to_interfaz_usuario_base"] is True
    assert first["strict_comparability_reason"] == "parity_proxy_ready"
    assert second["strict_comparability_reason"] == "parity_proxy_ready"
