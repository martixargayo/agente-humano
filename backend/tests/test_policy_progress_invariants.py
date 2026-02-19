from __future__ import annotations

from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.nodes.policy_progress_node import policy_progress_node
from negotiation.policy_progress import update_policy_state
from negotiation.progress_updater import update_progress_state
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_policy_state,
    default_progress_state,
    default_world_state,
)
from negotiation.state.deps import AgentDeps


def test_progress_updater_aligns_policy_state_on_new_policy():
    prev_progress = default_progress_state()
    prev_progress["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "rapport_build",
    }
    decision = default_policy_decision()
    decision["policy_id"] = "test_credibility"

    progress = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=decision,
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=None,
        belief_state=default_belief_state(),
        turn_count=2,
    )

    assert progress["policy_state"]["policy_id"] == "test_credibility"


def test_progress_updater_atomic_policy_stays_inactive():
    decision = default_policy_decision()
    decision["policy_id"] = "safe_neutral"

    progress = update_progress_state(
        prev_progress=default_progress_state(),
        policy_decision=decision,
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=None,
        belief_state=default_belief_state(),
        turn_count=1,
    )

    assert progress["policy_state"]["status"] == "inactive"
    assert progress["policy_state"]["planner_request"] == "choose_policy"


def test_policy_hint_uses_current_step_next_action_hint():
    policy_state = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
    }

    updated_state, policy_hint, _meta = update_policy_state(
        prev_policy_state=policy_state,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=3,
        last_policy_executed=None,
    )

    assert updated_state["policy_id"] == "test_credibility"
    assert policy_hint["next_action_hint"] == "Solicita datos verificables de la supuesta oferta."


def test_policy_progress_never_switches_policy_id_when_replanning():
    policy_state = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
        "step_attempts": 2,
    }

    updated_state, _hint, _meta = update_policy_state(
        prev_policy_state=policy_state,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=4,
        last_policy_executed=None,
    )

    assert updated_state["policy_id"] == "test_credibility"
    assert updated_state["planner_request"] in {"continue_policy", "replan_policy"}


def test_planner_skips_when_continue_policy_and_calls_when_replan():
    called = {"planner": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["planner"] += 1
        decision = default_policy_decision()
        decision["policy_id"] = "safe_neutral"
        phase_candidate = {
            "phase": "opening",
            "confidence": 0.5,
            "reasons": ["history:mock"],
            "signals": [],
            "alternatives": [],
        }
        return phase_candidate, decision, {"planner_meta": {"mock": True}}

    deps = AgentDeps(
        plan_phase_policy=fake_plan_phase_policy,
        update_belief_state=lambda **_kwargs: (default_belief_state(), {}),
        execute=lambda _messages: "ok",
    )

    state = {
        "deps": deps,
        "objective": "test",
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "hard_constraints_struct": {},
        "constraints": "",
        "recent_history_text": "",
        "world_diff": {},
        "turn_count": 1,
    }
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
        "planner_request": "continue_policy",
    }

    phase_policy_planner_node(dict(state))
    assert called["planner"] == 0

    replan_state = dict(state)
    replan_state["progress_state"] = default_progress_state()
    replan_state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "step_idx": 0,
        "planner_request": "replan_policy",
    }
    phase_policy_planner_node(replan_state)
    assert called["planner"] == 1


def test_progress_updater_adds_stuck_loop_flag_when_repeated_neutral_policy():
    prev_progress = default_progress_state()
    prev_progress["turns_in_same_mode"] = 1
    prev_progress["last_chosen_policy_id"] = "rapport_build"

    decision = default_policy_decision()
    decision["policy_id"] = "rapport_build"

    progress = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=decision,
        last_policy_executed={"policy_id": "rapport_build"},
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=2,
    )

    assert "stuck_in_policy" in progress["loop_flags"]


def test_progress_updater_clears_stuck_loop_flag_after_good_outcome():
    prev_progress = default_progress_state()
    prev_progress["loop_flags"] = ["stuck_in_policy"]
    prev_progress["turns_in_same_mode"] = 3
    prev_progress["last_chosen_policy_id"] = "deescalate_tension"

    tense_belief = default_belief_state()
    tense_belief["universal"]["dynamics"]["interaction_health"] = "tense"

    stable_belief = default_belief_state()
    stable_belief["universal"]["dynamics"]["interaction_health"] = "stable"

    decision = default_policy_decision()
    decision["policy_id"] = "deescalate_tension"

    progress = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=decision,
        last_policy_executed={"policy_id": "deescalate_tension"},
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=tense_belief,
        belief_state=stable_belief,
        turn_count=4,
    )

    assert progress["last_executed_policy_outcome"] == "good"
    assert "stuck_in_policy" not in progress["loop_flags"]


def test_policy_progress_uses_world_judgement_advance_step_when_enabled(monkeypatch):
    monkeypatch.setenv("POLICY_PLAN_JUDGE_ENABLED", "1")
    state = {
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "world_diff": {},
        "belief_diff": {},
        "user_message": "ok",
        "turn_count": 2,
        "policy_plan_judgement": {
            "plan_status": "advance_step",
            "why": "new info",
            "evidence": [{"quote": "dato"}],
            "confidence": 0.9,
        },
    }
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "planner_request": "continue_policy",
        "step_idx": 0,
    }

    result = policy_progress_node(state)
    assert result["progress_state"]["policy_state"]["planner_request"] == "continue_policy"
    assert result["progress_state"]["policy_state"]["step_idx"] == 1
    assert "world_judge:advance_step" in result["policy_meta"]["reasons"]


def test_policy_progress_disabled_flag_ignores_missing_judgement_streak(monkeypatch):
    monkeypatch.setenv("POLICY_PLAN_JUDGE_ENABLED", "0")
    state = {
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "world_diff": {},
        "belief_diff": {},
        "user_message": "ok",
        "turn_count": 3,
    }
    state["progress_state"]["active_plan_status"] = "active"
    state["progress_state"]["judgement_missing_streak"] = 10
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "planner_request": "continue_policy",
        "step_idx": 0,
    }

    result = policy_progress_node(state)
    assert "judgement_missing_streak" not in result["policy_meta"]["reasons"]
