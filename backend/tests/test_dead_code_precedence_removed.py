import importlib
import sys

from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from state import SessionState


def _fake_deps():
    def fake_plan_phase_policy(*_args, **_kwargs):
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, default_policy_decision(), {}

    def fake_update_belief_state(*_args, **_kwargs):
        return default_belief_state(), {"belief_update_skipped": False}

    def fake_execute(_messages):
        return "ok"

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_precedence_modules_removed(monkeypatch):
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )
    state = SessionState(user_id="dead", session_id="dead")
    state.world_state = default_world_state()
    state.progress_state = default_progress_state()
    run_negotiation_agent(state, "hola", deps=_fake_deps())

    assert "negotiation.precedence" not in sys.modules
    assert "negotiation.nodes.precedence_node" not in sys.modules
    assert importlib.util.find_spec("negotiation.precedence") is None
    assert importlib.util.find_spec("negotiation.nodes.precedence_node") is None
