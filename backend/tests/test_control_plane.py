from negotiation.negotiation_graph import AgentDeps, run_negotiation_agent
from negotiation.phase_state_updater import update_phase_state
from negotiation.policy_planner import plan_policy
from negotiation.schemas import (
    default_belief_state,
    default_intent_state,
    default_policy_decision,
    default_progress_state,
    default_world_state,
)
from state import SessionState


def _fake_deps(captured, belief_state):
    def fake_plan_policy(*args, **kwargs):
        decision = default_policy_decision()
        decision["policy_id"] = "rapport_build"
        return decision, {"planner_meta": {"mock": True}}

    def fake_update_belief_state(*args, **kwargs):
        return belief_state, {"belief_meta": {"mock": True}}

    def fake_execute(messages):
        captured["messages"] = messages
        return "ok"

    return AgentDeps(
        plan_policy=fake_plan_policy,
        update_belief_state=fake_update_belief_state,
        execute=fake_execute,
    )


def test_graph_precedence_pauses_intent(monkeypatch):
    captured = {}
    belief = default_belief_state()
    belief["dynamics"]["interaction_health"] = "tense"
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


def test_intent_forced_blocked_by_precedence_fallback():
    world_state = default_world_state()
    belief_state = default_belief_state()
    progress_state = default_progress_state()
    intent_hint = {
        "commitment_level": "hard",
        "step_kind": "close_next",
    }
    precedence = {
        "mode": "recovery_guard",
        "reason": "precedence:recovery_guard | precedence_reason:belief:health_tense",
        "min_policy_tags": ["safe_when_tense", "deescalation"],
        "block_policy_tags": ["aggressive"],
    }

    decision, meta = plan_policy(
        world_state=world_state,
        belief_state=belief_state,
        progress_state=progress_state,
        intent_hint=intent_hint,
        precedence=precedence,
        objective="Cerrar la compra",
        constraints="",
        recent_context="",
    )

    assert meta["planner_error"] == "intent_forced_blocked_by_precedence"
    assert meta["intent_preferred_blocked_by_precedence"] is True
    assert meta["allowed_policy_ids_base"]
    assert "allowed_policy_ids_after_precedence" in meta
    assert "allowed_policy_ids_after_intent" in meta
    assert meta["precedence_filtered_out"]
    assert decision["policy_id"] == "deescalate_tension"


def test_phase_hard_override_respects_precedence_block():
    prev_phase = default_progress_state()["phase_state"]
    world_state = default_world_state()
    world_state["price_firm"] = True
    belief_state = default_belief_state()
    precedence = {"phase_floor": "recovery", "allow_closing": False}

    phase, meta = update_phase_state(
        prev_phase_state=prev_phase,
        world_state=world_state,
        world_diff={"price_firm": {"before": False, "after": True}},
        belief_state=belief_state,
        intent_state=None,
        recent_history_text="",
        turn_count=2,
        precedence=precedence,
    )

    assert meta["phase_hard_override_used"] is True
    assert meta["phase_precedence_forced"] is True
    assert phase["phase"] == "recovery"
