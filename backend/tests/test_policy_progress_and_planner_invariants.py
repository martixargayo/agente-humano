from types import SimpleNamespace

from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.policy_progress import update_policy_state
from negotiation.schemas import (
    default_belief_state,
    default_policy_state,
    default_progress_state,
    default_world_state,
)


def _planner_state(progress_state):
    return {
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": progress_state,
        "objective": "",
        "constraints": "",
        "hard_constraints_struct": {},
        "recent_history_text": "",
        "turn_count": 1,
        "world_diff": {},
        "belief_diff": {},
        "allowed_policy_ids": ["safe_neutral"],
    }


def _minimal_active_plan():
    return {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [
            {"intent_id": "collect_new_signal", "what_to_do": "seguir", "safe_mode": "normal", "ask": []},
            {"intent_id": "pivot_signal", "what_to_do": "cerrar", "safe_mode": "normal", "ask": []},
        ],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
    }


def test_planner_skips_on_continue_same_step_when_reusable_policy_exists():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {}, {}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "active", "planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["active_plan"] = _minimal_active_plan()

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"plan_status": "continue_same_step", "skip_planner": False}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 0
    assert result["planner_meta"]["planner_skipped"] is True
    assert result["planner_meta"]["planner_skip_reason"] == "continue_same_step_without_planner"
    assert result["planner_meta"].get("planner_llm_called", False) is False


def test_planner_executes_when_judge_requires_change_even_with_advance_step():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {}, {}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "active", "planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["advance_step"] = True
    progress_state["active_plan"] = _minimal_active_plan()

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"plan_status": "advance_step", "skip_planner": False}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 1
    assert result["planner_meta"]["planner_skipped"] is False


def test_planner_runs_replan_when_advance_step_is_on_last_step():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "interests"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "active", "planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["advance_step"] = True
    plan = _minimal_active_plan()
    plan["current_step_idx"] = 1
    progress_state["active_plan"] = plan

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"plan_status": "advance_step", "skip_planner": False}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 1
    assert result["planner_meta"]["planner_skipped"] is False


def test_planner_skipped_when_judge_skip_planner_true_with_active_plan():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {}, {}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "active", "planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["active_plan"] = _minimal_active_plan()

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"skip_planner": True}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 0
    assert result["planner_meta"]["planner_skipped"] is True
    assert result["planner_meta"]["planner_skip_reason"] == "judge_skip_planner"
    assert result["planner_meta"].get("planner_llm_called", False) is False


def test_planner_called_when_replan_policy():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "climate"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "active", "planner_request": "replan_policy"})
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    phase_policy_planner_node(state)

    assert called["count"] == 1


def test_llm_failure_airbag_keeps_default_policy_decision():
    def fake_plan_phase_policy(**_kwargs):
        raise RuntimeError("boom")

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "inactive", "planner_request": "replan_policy"})
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert result["policy_decision"]["policy_id"]
    assert result["planner_meta"]["planner_failed"] is True


def test_policy_progress_completed_maps_to_replan():
    prev_policy_state = default_policy_state()
    prev_policy_state.update({"status": "active", "planner_request": "continue_policy"})

    updated, _hint, _meta = update_policy_state(
        prev_policy_state=prev_policy_state,
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=1,
        policy_plan_judgement={"plan_status": "completed"},
    )

    assert updated["planner_request"] == "replan_policy"


def test_policy_progress_continue_same_step_defaults_to_continue_policy(monkeypatch):
    monkeypatch.delenv("PLANNER_FORCE_REPLAN_ON_CONTINUE_SAME_STEP", raising=False)
    updated, _hint, _meta = update_policy_state(
        prev_policy_state=default_policy_state(),
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=1,
        policy_plan_judgement={"plan_status": "continue_same_step"},
    )

    assert updated["planner_request"] == "continue_policy"


def test_policy_progress_continue_same_step_can_force_replan_with_flag(monkeypatch):
    monkeypatch.setenv("PLANNER_FORCE_REPLAN_ON_CONTINUE_SAME_STEP", "1")
    updated, _hint, _meta = update_policy_state(
        prev_policy_state=default_policy_state(),
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=1,
        policy_plan_judgement={"plan_status": "continue_same_step"},
    )

    assert updated["planner_request"] == "replan_policy"


def test_planner_forces_replan_when_same_step_counter_reaches_threshold():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "climate"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    progress_state["same_step_no_progress_turns"] = 1
    policy_state = default_policy_state()
    policy_state.update({"planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["active_plan"] = _minimal_active_plan()

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"plan_status": "continue_same_step", "skip_planner": False}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    out = phase_policy_planner_node(state)
    assert called["count"] == 1
    assert out["planner_meta"]["planner_skipped"] is False
    assert "force_replan_no_progress_2nd_attempt" in out["planner_gate_debug"]["reason_codes"]


def test_planner_forces_replan_when_advisor_repeat_slot_2x():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "climate"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"planner_request": "continue_policy", "policy_id": "safe_neutral"})
    progress_state["policy_state"] = policy_state
    progress_state["active_plan"] = _minimal_active_plan()

    state = _planner_state(progress_state)
    state["policy_plan_judgement"] = {"plan_status": "continue_same_step", "skip_planner": False}
    state["advisor_recs"] = {"loop_or_waste_flags": ["repeat_slot_2x:documentacion"]}
    state["advisor_signals"] = {"force_replan": True, "blocked_topics": ["documentacion"], "block_ttl_turns": 2}
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    out = phase_policy_planner_node(state)
    assert called["count"] == 1
    assert out["planner_meta"]["planner_skipped"] is False
    assert "force_replan_advisor_repeat" in out["planner_gate_debug"]["reason_codes"]
