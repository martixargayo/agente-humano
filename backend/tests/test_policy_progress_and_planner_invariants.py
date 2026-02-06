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
    }


def test_planner_not_called_when_continue_policy():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {}, {}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "planner_request": "continue_policy",
        }
    )
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 0
    assert result["policy_decision"]["policy_id"] == "test_credibility"
    assert result["phase_candidate"] is None


def test_planner_called_when_choose_policy():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "opening"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "inactive", "planner_request": "choose_policy"})
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    phase_policy_planner_node(state)

    assert called["count"] == 1


def test_planner_called_when_replan_policy():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {"phase": "opening"}, {"policy_id": "safe_neutral"}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "planner_request": "replan_policy",
        }
    )
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    phase_policy_planner_node(state)

    assert called["count"] == 1


def test_llm_failure_airbag_safe_neutral():
    def fake_plan_phase_policy(**_kwargs):
        raise RuntimeError("boom")

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "inactive", "planner_request": "choose_policy"})
    progress_state["policy_state"] = policy_state

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert result["policy_decision"]["policy_id"] == "safe_neutral"
    assert result["planner_meta"]["planner_failed"] is True


def test_step_advances_on_slot_filled():
    prev_policy_state = default_policy_state()
    prev_policy_state.update(
        {
            "status": "active",
            "policy_id": "test_credibility",
            "step_idx": 0,
            "step_attempts": 0,
            "planner_request": "continue_policy",
        }
    )

    world_state = default_world_state()
    world_state["negotiation"]["evidence_offered"] = True

    updated, _hint, _meta = update_policy_state(
        prev_policy_state=prev_policy_state,
        world_state=world_state,
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=default_progress_state(),
        user_message="",
        turn_count=1,
    )

    assert updated["step_idx"] == 1
