from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from state import SessionState


def _fake_deps(captured, belief_state):
    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return belief_state, {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_graph_precedence_pauses_intent(monkeypatch):
    captured = {}
    belief = default_belief_state()
    belief["universal"]["dynamics"]["interaction_health"] = "tense"
    deps = _fake_deps(captured, belief)

    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    def fake_update_world_state(_prev_world, _user_message, **_kwargs):
        return default_world_state(), {"extractor_used": False}

    monkeypatch.setattr(
        "negotiation.negotiation_graph.update_world_state",
        fake_update_world_state,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )

    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    progress = default_progress_state()
    intent = default_intent_state()
    intent["status"] = "active"
    intent["intent_type"] = "info_extract"
    progress["intent_state"] = intent
    state.progress_state = progress

    run_negotiation_agent(state, "hola", deps=deps)

    assert state.progress_state["intent_state"]["status"] == "paused"
