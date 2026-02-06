from __future__ import annotations

from .elementos.strategy_definitions import PolicyPlan, PolicyStep
from .policies import get_policy
from .schemas import PolicyHint, PolicyMeta, PolicyState, default_policy_state


def _get_dotted(data: dict, path: str) -> object:
    cur: object = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def evaluate_step_success(
    step: PolicyStep,
    world_state: dict,
    belief_state: dict,
    slots_filled: dict,
) -> bool:
    for cond in step.success_if:
        if cond.kind == "slot_filled":
            if cond.key not in slots_filled:
                return False
        elif cond.kind == "world_flag_true":
            if not bool(_get_dotted(world_state, cond.key)):
                return False
        elif cond.kind == "belief_flag_eq":
            if _get_dotted(belief_state, cond.key) != cond.value:
                return False
        else:
            return False
    return True


def hydrate_slots_from_world(
    plan: PolicyPlan,
    world_state: dict,
    belief_state: dict,
    turn_count: int,
) -> dict:
    def _has_value(value: object) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict, tuple, set)):
            return len(value) > 0
        return True

    filled: dict = {}
    for slot in plan.slots_required:
        value = _get_dotted(world_state, slot)
        source = "world"
        if not _has_value(value):
            value = _get_dotted(belief_state, slot)
            source = "belief"
        if _has_value(value):
            filled[slot] = {"value": value, "source": source, "updated_turn": turn_count}
    return filled


def should_force_phase_recheck(
    world_state: dict,
    belief_state: dict,
    policy_state: dict,
) -> tuple[bool, str]:
    if bool(_get_dotted(world_state, "negotiation.phase_objective_met")):
        return True, "phase_objective_met"
    if _get_dotted(belief_state, "universal.dynamics.interaction_health") == "critical":
        return True, "interaction_health_critical"
    if policy_state.get("status") in {"succeeded", "abandoned"}:
        return True, "policy_terminal"
    return False, ""


def _build_policy_hint(policy_state: PolicyState, step: PolicyStep | None) -> PolicyHint:
    slots_required = policy_state.get("slots_required", [])
    slots_filled = policy_state.get("slots_filled", {})
    slots_missing = [slot for slot in slots_required if slot not in slots_filled]
    attempts_left = max(
        0, int(policy_state.get("max_attempts_per_step", 0)) - policy_state.get("step_attempts", 0)
    )
    return {
        "policy_active": policy_state.get("status") == "active",
        "policy_id": policy_state.get("policy_id", ""),
        "step_kind": step.kind if step else "",
        "target_slot": step.target_slot if step else "",
        "next_action_hint": step.next_action_hint if step else "",
        "attempts_left": attempts_left,
        "slots_missing": slots_missing,
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
) -> tuple[PolicyState, PolicyHint, PolicyMeta]:
    del world_diff, belief_diff, progress_state, user_message, last_policy_executed
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

    if policy_state.get("status") != "active":
        policy_state["planner_request"] = "choose_policy"
        meta["transition"] = "force_planner"
        meta["reasons"].append("policy_not_active")
        return policy_state, _build_policy_hint(policy_state, None), meta

    policy = get_policy(policy_state.get("policy_id", ""))
    plan = policy.plan if policy else None
    if not plan:
        policy_state["planner_request"] = "replan_policy"
        meta["transition"] = "force_planner"
        meta["reasons"].append("policy_no_plan")
        return policy_state, _build_policy_hint(policy_state, None), meta

    policy_state["max_attempts_per_step"] = int(plan.max_attempts_per_step)
    policy_state["slots_required"] = list(plan.slots_required)
    policy_state["slots_filled"] = hydrate_slots_from_world(
        plan, world_state, belief_state, turn_count
    )
    meta["thresholds"] = {
        "max_attempts_per_step": plan.max_attempts_per_step,
        "no_progress_turns_limit": plan.no_progress_turns_limit,
    }

    step_idx = int(policy_state.get("step_idx", 0))
    if step_idx >= len(plan.steps):
        policy_state["status"] = "succeeded"
        policy_state["planner_request"] = "replan_policy"
        meta["transition"] = "succeed"
        meta["reasons"].append("steps_completed")
        return policy_state, _build_policy_hint(policy_state, None), meta

    step = plan.steps[step_idx]
    success = evaluate_step_success(step, world_state, belief_state, policy_state["slots_filled"])
    if success:
        policy_state["step_idx"] = step_idx + 1
        policy_state["step_attempts"] = 0
        policy_state["no_progress_turns"] = 0
        meta["transition"] = "advance"
        meta["deltas"] = {"step_idx": policy_state["step_idx"]}
        if policy_state["step_idx"] >= len(plan.steps):
            policy_state["status"] = "succeeded"
            policy_state["planner_request"] = "replan_policy"
            meta["transition"] = "succeed"
            meta["reasons"].append("steps_completed")
        else:
            policy_state["planner_request"] = "continue_policy"
    else:
        policy_state["step_attempts"] = int(policy_state.get("step_attempts", 0)) + 1
        policy_state["no_progress_turns"] = int(policy_state.get("no_progress_turns", 0)) + 1
        if (
            policy_state["step_attempts"] >= plan.max_attempts_per_step
            or policy_state["no_progress_turns"] >= plan.no_progress_turns_limit
        ):
            policy_state["planner_request"] = "replan_policy"
            meta["transition"] = "force_planner"
            meta["reasons"].append("attempts_or_progress_exceeded")
        else:
            policy_state["planner_request"] = "continue_policy"
            meta["transition"] = "retry"

    force_phase, reason = should_force_phase_recheck(world_state, belief_state, policy_state)
    if force_phase and policy_state.get("planner_request") == "continue_policy":
        policy_state["planner_request"] = "replan_policy"
        meta["transition"] = "force_planner"
        meta["reasons"].append(f"phase_recheck:{reason}")

    return policy_state, _build_policy_hint(policy_state, step), meta
