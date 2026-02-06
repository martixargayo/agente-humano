from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_policy_state,
    default_progress_state,
    default_world_state,
)
from state import SessionState


def _fake_deps(captured):
    def fake_plan_phase_policy(*args, **kwargs):
        decision = default_policy_decision()
        allowed = kwargs.get("allowed_policy_ids") or []
        decision["policy_id"] = allowed[0] if allowed else "info_extract_critical"
        decision["micro_goal"] = "Pedir información clave."
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return default_belief_state(), {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    return AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def _queue_world_states(monkeypatch, world_states):
    queue = list(world_states)

    def fake_update_world_state(_prev_world, _user_message, **_kwargs):
        if queue:
            return queue.pop(0), {"extractor_used": False}
        return default_world_state(), {"extractor_used": False}

    monkeypatch.setattr(
        "negotiation.nodes.world_node.update_world_state",
        fake_update_world_state,
    )
    monkeypatch.setattr(
        "negotiation.negotiation_graph.get_negotiation_rag_index",
        lambda: None,
    )


def test_integration_policy_state_hydrates(monkeypatch):
    captured = {}
    deps = _fake_deps(captured)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    world_turn1 = default_world_state()
    world_turn1["negotiation"]["other_buyer_claimed"] = True
    _queue_world_states(monkeypatch, [world_turn1])

    state = SessionState(user_id="u", session_id="s")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    state.progress_state = default_progress_state()

    run_negotiation_agent(state, "no sé", deps=deps)
    policy_state = state.progress_state["policy_state"]
    assert policy_state["policy_id"]
    assert policy_state["status"] in {"active", "inactive"}


def test_integration_replan_policy_rehydrates(monkeypatch):
    captured = {}
    deps = _fake_deps(captured)
    monkeypatch.setattr(
        "negotiation.negotiation_graph.normalize_text",
        lambda raw_reply, last_user_message=None: raw_reply,
    )

    world_turn = default_world_state()
    world_turn["negotiation"]["other_buyer_claimed"] = True
    _queue_world_states(monkeypatch, [world_turn])

    state = SessionState(user_id="u2", session_id="s2")
    state.world_state = default_world_state()
    state.belief_state = default_belief_state()
    progress = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "step_attempts": 0,
            "planner_request": "replan_policy",
        }
    )
    progress["policy_state"] = policy_state
    state.progress_state = progress

    run_negotiation_agent(state, "precio firme", deps=deps)
    policy_state = state.progress_state["policy_state"]
    assert policy_state["policy_id"]
