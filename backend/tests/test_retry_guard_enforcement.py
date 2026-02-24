from __future__ import annotations

from negotiation.policy_progress import update_policy_state
from negotiation.progress_updater import update_progress_state
from negotiation.nodes.planner_node import phase_policy_planner_node
from negotiation.nodes.executor_node import executor_node
from negotiation.schemas import (
    default_belief_state,
    default_policy_decision,
    default_policy_state,
    default_progress_state,
    default_world_state,
)
from negotiation.state.deps import AgentDeps


def _active_plan(intent_id: str = "collect_new_signal", with_intent: bool = True):
    step = {"step_idx": 0, "what_to_do": "seguir", "safe_mode": "normal", "ask": ["¿Qué dato concreto puedes darme?"]}
    if with_intent:
        step["intent_id"] = intent_id
    return {
        "plan_id": "p1",
        "current_step_idx": 0,
        "steps": [step, {"step_idx": 1, "intent_id": "pivot", "what_to_do": "pivot", "safe_mode": "normal", "ask": []}],
        "plan_constraints": {"max_questions_per_turn": 2, "must_avoid": [], "stop_conditions": []},
    }


def test_retry_guard_increments_on_continue_with_evidence(monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS_PER_INTENT_STEP", "2")
    progress = default_progress_state()
    progress["active_plan"] = _active_plan()
    progress["last_judgement_status"] = "continue_same_step"

    progress = update_progress_state(
        prev_progress=progress,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=1,
        policy_plan_judgement={"plan_status": "continue_same_step", "evidence": [{"quote": "dato"}]},
        active_plan=_active_plan(),
    )
    assert progress["retry_guard"]["attempts"] == 1
    assert progress["retry_guard"]["reached"] is False

    progress["last_judgement_status"] = "continue_same_step"
    progress = update_progress_state(
        prev_progress=progress,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=2,
        policy_plan_judgement={"plan_status": "continue_same_step", "evidence": [{"quote": "dato2"}]},
        active_plan=_active_plan(),
    )
    assert progress["retry_guard"]["attempts"] == 2
    assert progress["retry_guard"]["reached"] is True


def test_retry_guard_resets_on_advance_step(monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS_PER_INTENT_STEP", "2")
    progress = default_progress_state()
    progress["active_plan"] = _active_plan()
    progress["plan_ledger"]["attempt_counters_by_key"] = {"p1:0:collect_new_signal": 2}
    progress["last_judgement_status"] = "advance_step"

    out = update_progress_state(
        prev_progress=progress,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=3,
        policy_plan_judgement={"plan_status": "advance_step", "evidence": [{"quote": "ok"}]},
        active_plan=_active_plan(),
    )
    assert out["retry_guard"]["attempts"] == 0
    assert out["retry_guard"]["reached"] is False


def test_policy_progress_forces_replan_when_retry_guard_reached():
    progress = default_progress_state()
    progress["retry_guard"] = {
        "active_key": "p1:0:collect_new_signal",
        "intent_id": "collect_new_signal",
        "plan_id": "p1",
        "step_idx": 0,
        "attempts": 2,
        "max_attempts": 2,
        "reached": True,
        "reason": "continue_same_step_in_line",
    }
    updated, _, meta = update_policy_state(
        prev_policy_state=default_policy_state(),
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
    assert "force_replan_max_attempts" in meta.get("reasons", [])


def test_planner_node_forces_replan_when_retry_guard_reached():
    called = {"planner": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["planner"] += 1
        return {}, default_policy_decision(), {}

    deps = AgentDeps(plan_phase_policy=fake_plan_phase_policy, update_belief_state=lambda **_kwargs: (default_belief_state(), {}), execute=lambda _messages: "ok")
    state = {
        "deps": deps,
        "objective": "x",
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "hard_constraints_struct": {},
        "constraints": "",
        "recent_history_text": "",
        "world_diff": {},
        "turn_count": 3,
        "policy_plan_judgement": {"skip_planner": False},
    }
    state["progress_state"]["policy_state"] = {**default_policy_state(), "policy_id": "safe_neutral", "planner_request": "continue_policy"}
    state["progress_state"]["active_plan"] = _active_plan()
    state["progress_state"]["retry_guard"] = {
        "active_key": "p1:0:collect_new_signal",
        "intent_id": "collect_new_signal",
        "plan_id": "p1",
        "step_idx": 0,
        "attempts": 2,
        "max_attempts": 2,
        "reached": True,
        "reason": "continue_same_step_in_line",
    }
    out = phase_policy_planner_node(state)
    assert called["planner"] == 1
    assert out["planner_meta"]["pivot_required"] is True
    assert out["planner_meta"].get("retry_guard_enforced") is True


def test_executor_blocks_repeated_question_when_retry_guard_reached(monkeypatch):
    def fake_render(*args, **kwargs):
        return {"response_text": "¿Qué dato concreto puedes darme?", "asked_question": True}

    monkeypatch.setattr("negotiation.nodes.executor_node.render_executor_output", fake_render)
    state = {
        "deps": AgentDeps(plan_phase_policy=lambda **_: ({}, default_policy_decision(), {}), update_belief_state=lambda **_: (default_belief_state(), {}), execute=lambda _messages: "ok"),
        "objective": "x",
        "user_message": "hola",
        "policy_decision": default_policy_decision(),
        "progress_state": default_progress_state(),
        "world_state": default_world_state(),
    }
    state["progress_state"]["active_plan"] = _active_plan()
    state["progress_state"]["retry_guard"] = {
        "active_key": "p1:0:collect_new_signal",
        "intent_id": "collect_new_signal",
        "plan_id": "p1",
        "step_idx": 0,
        "attempts": 2,
        "max_attempts": 2,
        "reached": True,
        "reason": "continue_same_step_in_line",
    }
    state["progress_state"]["plan_ledger"]["asked_questions_recent"] = ["¿Qué dato concreto puedes darme?"]
    out = executor_node(state)
    assert out["assistant_message"] != "¿Qué dato concreto puedes darme?"
    assert out["executor_validator_meta"]["question_blocked_due_to_retry_guard"] is True


def test_integration_four_turns_forces_pivot(monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS_PER_INTENT_STEP", "2")
    progress = default_progress_state()
    progress["active_plan"] = _active_plan()

    for turn in [1, 2]:
        progress["last_judgement_status"] = "continue_same_step"
        progress = update_progress_state(
            prev_progress=progress,
            policy_decision=default_policy_decision(),
            last_policy_executed=None,
            prev_world_state=default_world_state(),
            world_state=default_world_state(),
            prev_belief_state=default_belief_state(),
            belief_state=default_belief_state(),
            turn_count=turn,
            policy_plan_judgement={"plan_status": "continue_same_step", "evidence": [{"quote": "ok"}]},
            active_plan=_active_plan(),
        )

    assert progress["retry_guard"]["reached"] is True

    pstate, _, _ = update_policy_state(
        prev_policy_state={**default_policy_state(), "planner_request": "continue_policy", "policy_id": "safe_neutral"},
        world_state=default_world_state(),
        world_diff={},
        belief_state=default_belief_state(),
        belief_diff={},
        progress_state=progress,
        user_message="",
        turn_count=3,
        policy_plan_judgement={"plan_status": "continue_same_step"},
    )
    assert pstate["planner_request"] == "replan_policy"


def test_skip_planner_cannot_override_retry_guard():
    called = {"planner": 0}

    def fake_plan_phase_policy(**_kwargs):
        called["planner"] += 1
        return {}, default_policy_decision(), {}

    deps = AgentDeps(plan_phase_policy=fake_plan_phase_policy, update_belief_state=lambda **_kwargs: (default_belief_state(), {}), execute=lambda _messages: "ok")
    state = {
        "deps": deps,
        "objective": "x",
        "world_state": default_world_state(),
        "belief_state": default_belief_state(),
        "progress_state": default_progress_state(),
        "hard_constraints_struct": {},
        "constraints": "",
        "recent_history_text": "",
        "world_diff": {},
        "turn_count": 4,
        "policy_plan_judgement": {"skip_planner": True},
    }
    state["progress_state"]["policy_state"] = {**default_policy_state(), "policy_id": "safe_neutral", "planner_request": "continue_policy"}
    state["progress_state"]["active_plan"] = _active_plan()
    state["progress_state"]["retry_guard"] = {
        "active_key": "p1:0:collect_new_signal",
        "intent_id": "collect_new_signal",
        "plan_id": "p1",
        "step_idx": 0,
        "attempts": 3,
        "max_attempts": 2,
        "reached": True,
        "reason": "continue_same_step_in_line",
    }
    out = phase_policy_planner_node(state)
    assert called["planner"] == 1
    assert out["planner_meta"].get("retry_guard_blocked_judge_skip") is True


def test_legacy_step_without_intent_id_uses_no_intent_key(monkeypatch):
    monkeypatch.setenv("MAX_ATTEMPTS_PER_INTENT_STEP", "2")
    progress = default_progress_state()
    plan = _active_plan(with_intent=False)
    progress["active_plan"] = plan
    progress["last_judgement_status"] = "continue_same_step"
    out = update_progress_state(
        prev_progress=progress,
        policy_decision=default_policy_decision(),
        last_policy_executed=None,
        prev_world_state=default_world_state(),
        world_state=default_world_state(),
        prev_belief_state=default_belief_state(),
        belief_state=default_belief_state(),
        turn_count=1,
        policy_plan_judgement={"plan_status": "continue_same_step", "evidence": [{"quote": "ok"}]},
        active_plan=plan,
    )
    assert out["retry_guard"]["intent_id"] == "__no_intent__"
    assert out["retry_guard"]["active_key"].endswith(":__no_intent__")
