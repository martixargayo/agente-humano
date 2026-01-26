# backend/negotiation/progress_updater.py
from __future__ import annotations

from .schemas import BeliefState, PolicyDecision, ProgressState, WorldState, default_progress_state
from .world_state_updater import diff_world_state


def _has_info_delta(world_diff: dict) -> bool:
    info_keys = {
        "docs_claimed",
        "docs_types",
        "deadline_claimed",
        "deadline_text",
        "other_buyer_claimed",
        "concession_made",
        "concession_text",
        "price_mentioned",
        "price_value",
    }
    return any(key in world_diff for key in info_keys)


def _evaluate_outcome(
    policy_id: str,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
) -> str:
    if not policy_id:
        return "neutral"

    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")
    prev_health = (
        prev_belief_state.get("dynamics", {}).get("interaction_health", "stable")
        if prev_belief_state
        else "stable"
    )
    world_diff = diff_world_state(prev_world_state, world_state)

    if policy_id == "info_extract_critical":
        if _has_info_delta(world_diff):
            return "good"
        return "neutral"

    if policy_id == "delay_price_discussion":
        if world_state.get("price_mentioned") and not prev_world_state.get("price_mentioned"):
            return "bad"
        if _has_info_delta(world_diff):
            return "good"
        return "neutral"

    if policy_id == "deescalate_tension":
        if health == "stable" and prev_health != "stable":
            return "good"
        if health == "tense":
            return "bad"
        return "neutral"

    if policy_id == "rapport_build":
        if health == "stable" and prev_health != "stable":
            return "good"
        return "neutral"

    if policy_id == "test_credibility":
        if _has_info_delta(world_diff):
            return "good"
        return "neutral"

    if policy_id in {"tradeoff_offer", "hold_position"}:
        if world_state.get("concession_made") and not prev_world_state.get("concession_made"):
            return "good"
        return "neutral"

    if policy_id == "challenge_anchor_indirect":
        if belief_state.get("stance", {}).get("seller_flexibility", 0.0) > 0.6:
            return "good"
        return "neutral"

    if policy_id == "close_with_conditions":
        if world_state.get("concession_made") and not prev_world_state.get("concession_made"):
            return "good"
        return "neutral"

    return "neutral"


def update_progress_state(
    prev_progress: ProgressState | None,
    policy_decision: PolicyDecision,
    last_policy_executed: PolicyDecision | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    prev_belief_state: BeliefState | None,
    belief_state: BeliefState,
) -> ProgressState:
    progress = default_progress_state()
    if prev_progress:
        progress.update(prev_progress)

    previous_policy_id = last_policy_executed.get("policy_id", "") if last_policy_executed else ""
    if previous_policy_id:
        progress["last_executed_policy_id"] = previous_policy_id
        progress["last_executed_policy_outcome"] = _evaluate_outcome(
            previous_policy_id,
            prev_world_state,
            world_state,
            prev_belief_state,
            belief_state,
        )

    policy_id = policy_decision.get("policy_id", "")
    if policy_id:
        attempts = dict(progress.get("policy_attempts", {}))
        attempts[policy_id] = attempts.get(policy_id, 0) + 1
        progress["policy_attempts"] = attempts

        last_chosen_policy_id = ""
        if prev_progress:
            last_chosen_policy_id = prev_progress.get("last_chosen_policy_id", "")
        if last_chosen_policy_id == policy_id:
            progress["turns_in_same_mode"] = prev_progress.get("turns_in_same_mode", 0) + 1
        else:
            progress["turns_in_same_mode"] = 1
        progress["last_chosen_policy_id"] = policy_id

    loop_flags = list(progress.get("loop_flags", []))
    if (
        progress.get("turns_in_same_mode", 0) >= 2
        and progress.get("last_executed_policy_outcome") != "good"
    ):
        if "stuck_in_policy" not in loop_flags:
            loop_flags.append("stuck_in_policy")
    progress["loop_flags"] = loop_flags

    return progress
