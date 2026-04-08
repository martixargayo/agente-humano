from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from negociacion.optimizador import services as opt_services
from sessions.state import SessionState, get_session_store


def test_optimizer_list_contexts_and_prompts_cover_both_flows() -> None:
    get_session_store().clear()
    contexts = opt_services.list_contexts()
    flows = {(item["flow_id"], item["context_id"]) for item in contexts}
    assert ("negociacion", "baseline_current") in flows
    assert ("conversacion_simple", "baseline") in flows

    opt_services.ensure_session(user_id="u", session_id="s", context_id="baseline")
    prompts = opt_services.list_prompts(user_id="u", session_id="s")
    assert [p["node"] for p in prompts] == ["brain"]


def test_optimizer_compare_cross_flow_fails_controlled() -> None:
    get_session_store().clear()
    state = SessionState(user_id="u", session_id="s")
    state.world_state["_session_surface"] = "optimizador"
    state.world_state["negotiation_canonical_traces"] = [
        {"turn_id": "a", "_optimizador": {"base_context": {"flow_id": "negociacion", "context_id": "baseline_current"}}},
        {"turn_id": "b", "_optimizador": {"base_context": {"flow_id": "conversacion_simple", "context_id": "baseline"}}},
    ]
    get_session_store().save(state)

    with pytest.raises(ValueError, match="cross_flow_compare_not_supported"):
        opt_services.compare_turns("a", "b")
