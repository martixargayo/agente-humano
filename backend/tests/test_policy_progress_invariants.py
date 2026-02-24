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


def test_policy_progress_maps_advance_step_to_continue_and_flag():
    state = {
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "world_diff": {},
        "belief_diff": {},
        "user_message": "ok",
        "turn_count": 2,
        "policy_plan_judgement": {"plan_status": "advance_step"},
    }
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "test_credibility",
        "planner_request": "continue_policy",
    }

    result = policy_progress_node(state)
    assert result["progress_state"]["policy_state"]["planner_request"] == "continue_policy"
    assert result["progress_state"]["advance_step"] is True



def test_policy_progress_maps_continue_same_step_to_replan_and_no_advance():
    progress = default_progress_state()
    policy_state = {**default_policy_state(), "status": "active", "planner_request": "continue_policy"}
    updated, _hint, _meta = update_policy_state(
        prev_policy_state=policy_state,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=progress,
        user_message="",
        turn_count=1,
        policy_plan_judgement={"plan_status": "continue_same_step"},
    )
    assert updated["planner_request"] == "replan_policy"
    assert progress["advance_step"] is False


def test_policy_progress_missing_judgement_falls_back_to_replan():
    progress = default_progress_state()
    policy_state = {**default_policy_state(), "status": "active", "planner_request": "continue_policy"}
    updated, _hint, meta = update_policy_state(
        prev_policy_state=policy_state,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=progress,
        user_message="",
        turn_count=1,
        policy_plan_judgement=None,
    )
    assert updated["planner_request"] == "replan_policy"
    assert "world_judge:interrupted_replan" in meta["reasons"]


def test_planner_does_not_skip_when_continue_policy_and_active_plan_present_without_advance():
    called = {"planner": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["planner"] += 1
        return {}, default_policy_decision(), {}

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
        "allowed_policy_ids": ["safe_neutral"],
    }
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "safe_neutral",
        "planner_request": "continue_policy",
    }
    state["progress_state"]["active_plan"] = {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [{"what_to_do": "seguir", "safe_mode": "normal", "ask": []}, {"what_to_do": "cerrar", "safe_mode": "normal", "ask": []}],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
    }

    result = phase_policy_planner_node(dict(state))
    assert called["planner"] == 1
    assert result["planner_meta"]["planner_skipped"] is False
    assert result["planner_debug"]["gate_decision"]["gate_path"] in {"replan_call_llm", "replan_missing_policy"}
    assert result["planner_debug"]["llm_call"]["planner_llm_called"] is True
    assert result["planner_debug"]["policy_selection"]["allowed_policy_ids_count"] >= 1
    assert result["planner_debug"]["executor_instruction_contract"]["plan_id"].startswith("plan_t")



def test_planner_skips_only_when_advance_step_true():
    called = {"planner": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["planner"] += 1
        return {}, default_policy_decision(), {}

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
        "allowed_policy_ids": ["safe_neutral"],
        "policy_plan_judgement": {"plan_status": "advance_step"},
    }
    state["progress_state"]["policy_state"] = {
        **default_policy_state(),
        "status": "active",
        "policy_id": "safe_neutral",
        "planner_request": "continue_policy",
    }
    state["progress_state"]["advance_step"] = True
    state["progress_state"]["active_plan"] = {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [{"what_to_do": "seguir", "safe_mode": "normal", "ask": []}, {"what_to_do": "cerrar", "safe_mode": "normal", "ask": []}],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
    }

    result = phase_policy_planner_node(dict(state))
    assert called["planner"] == 0
    assert result["planner_meta"]["planner_skipped"] is True
    assert result["planner_meta"]["planner_skip_reason"] == "advance_step_without_planner"


def test_progress_updater_tracks_continue_loop_flag():
    prev_progress = default_progress_state()
    prev_progress["last_judgement_status"] = "continue_same_step"
    prev_progress["no_progress_same_step_turns"] = 2
    decision = default_policy_decision()
    progress = update_progress_state(
        prev_progress=prev_progress,
        policy_decision=decision,
        last_policy_executed={"policy_id": decision["policy_id"]},
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=2,
    )
    assert "continue_loop" in progress["loop_flags"]
