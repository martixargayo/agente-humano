from __future__ import annotations

from ..policies import POLICIES
from ..schemas import IntentHint

__all__ = ["_preferred_policy_ids", "apply_intent_constraints"]

_POLICY_BY_ID = {policy.policy_id: policy for policy in POLICIES}


def _step_kind_to_caps(step_kind: str) -> set[str]:
    if not step_kind:
        return set()
    return {step_kind}


def _preferred_policy_ids(intent_hint: IntentHint | None) -> list[str]:
    if not intent_hint:
        return []
    step_kind = intent_hint.get("step_kind", "")
    required_caps = _step_kind_to_caps(step_kind)
    if not required_caps:
        return []
    preferred = [
        policy.policy_id
        for policy in POLICIES
        if policy.capabilities and required_caps.issubset(policy.capabilities)
    ]
    return preferred


def apply_intent_constraints(
    allowed: list[str],
    intent_hint: IntentHint | None,
) -> tuple[list[str], list[str], dict]:
    meta = {
        "planner_mode": "",
        "planner_error": "",
        "planner_fallback_used": False,
    }
    preferred = _preferred_policy_ids(intent_hint)

    if not intent_hint:
        return allowed, preferred, meta

    if intent_hint.get("slots_missing"):
        allowed = [
            policy_id
            for policy_id in allowed
            if not (
                (policy := _POLICY_BY_ID.get(policy_id))
                and policy.guards
                and "requires_slot_complete" in policy.guards
            )
        ]
    commitment = intent_hint.get("commitment_level")
    if commitment == "hard" and preferred:
        forced = [policy_id for policy_id in preferred if policy_id in allowed]
        meta["planner_mode"] = "intent_forced"
        if forced:
            return forced, preferred, meta
        meta["planner_error"] = "intent_policy_unavailable"
        meta["planner_fallback_used"] = True
        return [], preferred, meta
    if commitment == "soft" and preferred:
        intersection = [policy_id for policy_id in preferred if policy_id in allowed]
        if intersection:
            rest = [policy_id for policy_id in allowed if policy_id not in intersection]
            meta["planner_mode"] = "intent_soft_ranked"
            return intersection + rest, preferred, meta
        meta["planner_mode"] = "intent_preferred_no_intersection"
        return allowed, preferred, meta

    meta["planner_mode"] = "no_intent_constraint"
    return allowed, preferred, meta
