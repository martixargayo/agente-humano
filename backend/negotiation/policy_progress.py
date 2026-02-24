from __future__ import annotations

import os

from .schemas import PolicyHint, PolicyMeta, PolicyState, default_policy_state


_ALLOWED_STATUS = {"continue_same_step", "advance_step", "completed", "interrupted_replan"}


def _build_policy_hint(policy_state: PolicyState) -> PolicyHint:
    return {
        "policy_active": bool(policy_state.get("status") == "active"),
        "policy_id": str(policy_state.get("policy_id", "")),
        "step_kind": "",
        "target_slot": "",
        "next_action_hint": "",
        "attempts_left": 0,
        "slots_missing": [],
    }


def update_policy_state(
    prev_policy_state: PolicyState | None,
    world_state: dict,
    world_diff: dict,
    belief_state: dict,
    belief_diff: dict,
    progress_state: dict,
    user_message: str,
    turn_count: int,
    last_policy_executed: dict | None = None,
    policy_plan_judgement: dict | None = None,
    active_plan_status: str = "none",
    judgement_missing_streak: int = 0,
) -> tuple[PolicyState, PolicyHint, PolicyMeta]:
    del world_state, world_diff, belief_state, belief_diff, user_message, last_policy_executed, active_plan_status, judgement_missing_streak

    policy_state = default_policy_state()
    if isinstance(prev_policy_state, dict):
        policy_state.update(prev_policy_state)
    policy_state["last_turn"] = turn_count
    if policy_state.get("started_turn", 0) == 0:
        policy_state["started_turn"] = turn_count

    meta: PolicyMeta = {
        "transition": "retry",
        "reasons": [],
        "deltas": {},
        "thresholds": {},
    }

    status = "interrupted_replan"
    if isinstance(policy_plan_judgement, dict):
        raw = str(policy_plan_judgement.get("plan_status", "")).strip()
        if raw in _ALLOWED_STATUS:
            status = raw

    progress_state["advance_step"] = status == "advance_step"

    force_replan_on_continue = os.getenv("PLANNER_FORCE_REPLAN_ON_CONTINUE_SAME_STEP", "0") == "1"

    if status == "continue_same_step":
        prev_active = str(policy_state.get("status", "") or "") == "active"
        if prev_active:
            policy_state["planner_request"] = "replan_policy"
            meta["transition"] = "force_planner"
            meta["reasons"].append("active_policy_continue_requires_replan")
        else:
            policy_state["planner_request"] = "replan_policy" if force_replan_on_continue else "continue_policy"
            meta["transition"] = "force_planner" if force_replan_on_continue else "retry"
            if force_replan_on_continue:
                meta["reasons"].append("config:force_replan_on_continue_same_step")
    elif status == "advance_step":
        policy_state["planner_request"] = "continue_policy"
        meta["transition"] = "advance"
        meta["deltas"] = {"advance_step": True}
    elif status == "completed":
        policy_state["planner_request"] = "replan_policy"
        policy_state["status"] = "succeeded"
        meta["transition"] = "succeed"
    else:
        policy_state["planner_request"] = "replan_policy"
        meta["transition"] = "force_planner"

    meta["reasons"].append(f"world_judge:{status}")
    return policy_state, _build_policy_hint(policy_state), meta
