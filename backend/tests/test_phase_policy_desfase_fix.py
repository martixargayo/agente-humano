from types import SimpleNamespace

import pytest

from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.policies import get_policy, policy_phase_catalog
from negotiation.policy_planner import allowed_policy_ids
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


def _choose_policy_ids(progress_state):
    world_state = default_world_state()
    belief_state = default_belief_state()
    allowed_all = allowed_policy_ids(
        world_state, belief_state, progress_state, constraints_struct={}
    )
    phase_catalog = policy_phase_catalog()
    closing_only = next(
        (
            policy_id
            for policy_id in allowed_all
            if "formalize" in phase_catalog.get(policy_id, [])
            and "climate" not in phase_catalog.get(policy_id, [])
        ),
        None,
    )
    opening_only = next(
        (
            policy_id
            for policy_id in allowed_all
            if "climate" in phase_catalog.get(policy_id, [])
            and "formalize" not in phase_catalog.get(policy_id, [])
        ),
        None,
    )
    opening_any = next(
        (
            policy_id
            for policy_id in allowed_all
            if "climate" in phase_catalog.get(policy_id, [])
        ),
        None,
    )
    return allowed_all, phase_catalog, closing_only, opening_only, opening_any


def test_policy_repaired_when_phase_effective_mismatch():
    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "inactive", "planner_request": "choose_policy"})
    progress_state["policy_state"] = policy_state

    allowed_all, phase_catalog, closing_only, opening_only, _opening_any = _choose_policy_ids(
        progress_state
    )
    if not closing_only or not opening_only:
        pytest.skip("No suitable policies found for phase mismatch test.")

    def fake_plan_phase_policy(**_kwargs):
        return (
            {
                "phase": "formalize",
                "confidence": 0.95,
                "reasons": [],
                "signals": [],
                "alternatives": [],
            },
            {
                "policy_id": opening_only,
                "reason": "",
                "micro_goal": "",
                "risk_posture": "low",
                "why_short": "",
                "inputs_used": [],
            },
            {},
        )

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    policy_id = result["policy_decision"]["policy_id"]
    assert policy_id in allowed_all
    assert "formalize" in phase_catalog.get(policy_id, [])
    assert result["planner_meta"]["policy_phase_mismatch"] is True


def test_hysteresis_hold_forces_policy_to_match_phase_effective():
    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_state.update({"status": "inactive", "planner_request": "choose_policy"})
    progress_state["policy_state"] = policy_state

    allowed_all, phase_catalog, closing_only, _opening_only, opening_any = _choose_policy_ids(
        progress_state
    )
    if not closing_only or not opening_any:
        pytest.skip("No suitable policies found for hysteresis test.")

    def fake_plan_phase_policy(**_kwargs):
        return (
            {
                "phase": "formalize",
                "confidence": 0.1,
                "reasons": [],
                "signals": [],
                "alternatives": [],
            },
            {
                "policy_id": closing_only,
                "reason": "",
                "micro_goal": "",
                "risk_posture": "low",
                "why_short": "",
                "inputs_used": [],
            },
            {},
        )

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    policy_id = result["policy_decision"]["policy_id"]
    assert policy_id in allowed_all
    assert "climate" in phase_catalog.get(policy_id, [])
    assert result["phase_effective"]["phase"] == "climate"


def test_no_regression_continue_policy_skips_planner():
    called = {"count": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["count"] += 1
        return {}, {}, {}

    progress_state = default_progress_state()
    policy_state = default_policy_state()
    policy_id = "safe_neutral"

    policy_state.update(
        {
            "status": "active",
            "policy_id": policy_id,
            "step_idx": 0,
            "planner_request": "continue_policy",
        }
    )
    progress_state["policy_state"] = policy_state
    progress_state["active_plan"] = {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [{"what_to_do": "seguir", "safe_mode": "normal", "ask": []}],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
    }

    state = _planner_state(progress_state)
    state["deps"] = SimpleNamespace(plan_phase_policy=fake_plan_phase_policy)

    result = phase_policy_planner_node(state)

    assert called["count"] == 0
    assert result["policy_decision"]["policy_id"] == policy_id
