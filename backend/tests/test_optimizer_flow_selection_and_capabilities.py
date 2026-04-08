from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import HTTPException

from negociacion.optimizador import context_bridge
from negociacion.optimizador import services as opt_services
from negociacion.optimizador import trace_reader
from negociacion.optimizador.flow_adapters import ConversacionSimpleOptimizerAdapter
from sessions.state import SessionState, get_session_store


def test_flow_selection_and_context_selection_conversacion_simple() -> None:
    get_session_store().clear()
    payload = opt_services.ensure_session(user_id="u", session_id="s", flow_id="conversacion_simple", context_id="baseline")
    assert payload["base_context"]["flow_id"] == "conversacion_simple"
    assert payload["base_context"]["context_id"] == "baseline"
    assert payload["capabilities"]["supports_single_node_trace"] is True


def test_context_listing_filtered_by_flow() -> None:
    cs_contexts = opt_services.list_contexts(flow_id="conversacion_simple")
    neg_contexts = opt_services.list_contexts(flow_id="negociacion")
    assert cs_contexts and all(item["flow_id"] == "conversacion_simple" for item in cs_contexts)
    assert neg_contexts and all(item["flow_id"] == "negociacion" for item in neg_contexts)


def test_invalid_flow_context_combination_rejected() -> None:
    get_session_store().clear()
    with pytest.raises(HTTPException) as exc:
        opt_services.ensure_session(user_id="u", session_id="s", flow_id="negociacion", context_id="baseline")
    assert exc.value.status_code == 404
    assert "unsupported_context_id" in str(exc.value.detail)


def test_list_prompts_uses_adapter_by_flow() -> None:
    get_session_store().clear()
    opt_services.ensure_session(user_id="u", session_id="s", flow_id="conversacion_simple", context_id="baseline")
    prompts = opt_services.list_prompts(user_id="u", session_id="s")
    assert [p["node"] for p in prompts] == ["brain"]


def test_compare_same_flow_supported_and_cross_flow_rejected() -> None:
    get_session_store().clear()
    state = SessionState(user_id="u", session_id="s")
    state.world_state["_session_surface"] = "optimizador"
    state.world_state["negotiation_canonical_traces"] = [
        {"turn_id": "n1", "_optimizador": {"base_context": {"flow_id": "negociacion", "context_id": "baseline_current"}}},
        {"turn_id": "n2", "_optimizador": {"base_context": {"flow_id": "negociacion", "context_id": "baseline_current"}}},
    ]
    get_session_store().save(state)

    payload = opt_services.compare_turns("n1", "n2")
    assert payload["a"]["turn_id"] == "n1"

    state.world_state["negotiation_canonical_traces"].append(
        {"turn_id": "c1", "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline"}}}
    )
    get_session_store().save(state)
    with pytest.raises(ValueError, match="cross_flow_compare_not_supported"):
        opt_services.compare_turns("n1", "c1")


def test_sandbox_turn_uses_correct_flow_adapter(monkeypatch) -> None:
    get_session_store().clear()
    opt_services.ensure_session(user_id="u", session_id="s", flow_id="conversacion_simple", context_id="baseline")

    called = {"cs": 0}

    def _fake_adapter_run(self, **kwargs):
        called["cs"] += 1
        state = kwargs["state"]
        state.world_state.setdefault("conversation_simple_canonical_traces", []).append({"turn_id": "t", "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline"}}})
        return "ok", state, {"entry_contract": {}, "latest_turn_id": "t"}

    monkeypatch.setattr(ConversacionSimpleOptimizerAdapter, "run_sandbox_turn", _fake_adapter_run)
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.resolve_entries", lambda **_: [])
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.apply_overrides", lambda base_config, entries, context_id=None: (base_config, None))
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.describe_effective_overrides", lambda entries: {"prompt": {}, "config": {}, "contextual": {}})
    monkeypatch.setattr("negociacion.optimizador.services.experiments_bridge.get_state", lambda optimizer_session_id: {"mode": "mirror", "workspace_version": 1})

    out = opt_services.run_sandbox_turn(
        optimizer_session_id="o",
        user_id="u",
        session_id="s",
        message="hola",
        conversation_id=None,
        scope_turn_id=None,
        repeat_from_turn_id=None,
    )
    assert out["reply"] == "ok"
    assert called["cs"] == 1


def test_trace_normalization_supports_multi_node_and_single_node_flows() -> None:
    get_session_store().clear()
    neg_state = SessionState(user_id="u", session_id="s-neg")
    neg_state.world_state["_session_surface"] = "optimizador"
    neg_state.world_state["negotiation_canonical_traces"] = [
        {
            "turn_id": "n1",
            "conversation_id_after": "conv-1",
            "logs": [{"source": "model"}],
            "nodes": {"planner": {"status": "ok", "model_called": True}},
            "_optimizador": {"base_context": {"flow_id": "negociacion", "context_id": "baseline_current", "context_version": "1.0.0"}},
        }
    ]
    get_session_store().save(neg_state)

    cs_state = SessionState(user_id="u", session_id="s-cs")
    cs_state.world_state["_session_surface"] = "optimizador"
    cs_state.world_state["conversation_simple_canonical_traces"] = [
        {
            "turn_id": "c1",
            "conversation_id_after": "conv-2",
            "logs": [{"source": "model"}],
            "nodes": {"brain": {"status": "ok", "model_called": True}},
            "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline", "context_version": "1.0.0"}},
        }
    ]
    get_session_store().save(cs_state)

    neg_turns = trace_reader.list_turns(user_id="u", session_id="s-neg")
    cs_turns = trace_reader.list_turns(user_id="u", session_id="s-cs")

    assert neg_turns[0]["flow_id"] == "negociacion"
    assert neg_turns[0]["context_id"] == "baseline_current"
    assert cs_turns[0]["flow_id"] == "conversacion_simple"
    assert cs_turns[0]["context_id"] == "baseline"


def test_frontend_exposes_flow_and_context_selection_controls() -> None:
    app_js = (ROOT / "avatar_app" / "optimizador" / "app.js").read_text(encoding="utf-8")
    assert "id='flowSelector'" in app_js
    assert "id='contextSelector'" in app_js
    assert "flow_id: state.selectedFlowId" in app_js
    assert "filteredContexts()" in app_js


def test_frontend_chat_send_and_poll_use_real_message_text() -> None:
    app_js = (ROOT / "avatar_app" / "optimizador" / "app.js").read_text(encoding="utf-8")
    assert 'body: JSON.stringify({ optimizer_session_id: state.optimizerSessionId, user_id: s.user_id, session_id: s.session_id, message' in app_js
    assert 'state.dialogue.map((d) => `<div class=\'msg ${d.role}\'>${d.role === "user" ? "Usuario" : "IA"}: ${escapeHtml(d.text || "")}</div>`).join("")' in app_js


def test_context_bridge_requires_flow_when_context_is_ambiguous(monkeypatch) -> None:
    get_session_store().clear()
    state = SessionState(user_id="u", session_id="s")
    monkeypatch.setattr(context_bridge, "resolve_negotiation_context", lambda context_id: object())
    monkeypatch.setattr(context_bridge, "resolve_conversacion_simple_context", lambda context_id: object())
    with pytest.raises(ValueError, match="ambiguous_context_id_requires_flow"):
        context_bridge.ensure_optimizer_session_context(state=state, requested_context_id="baseline")


def test_context_bridge_rejects_unsupported_flow_id() -> None:
    get_session_store().clear()
    state = SessionState(user_id="u", session_id="s")
    with pytest.raises(ValueError, match="unsupported_flow_id:foobar"):
        context_bridge.ensure_optimizer_session_context(state=state, requested_flow_id="foobar")
