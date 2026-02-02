# backend/negotiation/policy_planner.py
from __future__ import annotations

from .elementos.strategy_definitions import PHASE_INDEX
from .policies import POLICIES, list_policy_ids
from .schemas import (
    BeliefState,
    IntentHint,
    NegotiationPhase,
    ProgressState,
    WorldState,
)


_POLICY_BY_ID = {policy.policy_id: policy for policy in POLICIES}


def _phase_bonus(policy_phases: list[str], current_phase: str) -> int:
    if not policy_phases:
        return 0
    if current_phase == "recovery":
        if "recovery" in policy_phases:
            return 3
        return 0
    if current_phase in policy_phases:
        return 2
    if "recovery" in policy_phases:
        return 1
    if current_phase in PHASE_INDEX:
        cur_i = PHASE_INDEX[current_phase]  # type: ignore[index]
        for phase in policy_phases:
            if phase in PHASE_INDEX and abs(PHASE_INDEX[phase] - cur_i) == 1:
                return 1
    return 0


def repair_policy_by_phase(
    chosen_id: str,
    allowed_ids: list[str],
    policy_catalog: dict[str, list[str]],
    current_phase: str,
    preferred_ids: list[str] | None,
    commitment_level: str | None,
    policy_attempts: dict[str, int] | None,
) -> tuple[str, dict]:
    attempts = policy_attempts or {}
    meta = {
        "phase_repair_used": False,
        "phase_repair_from": chosen_id,
        "phase_repair_to": chosen_id,
        "phase_repair_mode": "",
        "phase_repair_attempts_blocked": [],
    }
    if commitment_level == "hard":
        meta["phase_repair_mode"] = "disabled_intent_hard"
        return chosen_id, meta

    scope = allowed_ids
    if preferred_ids:
        intersection = [policy_id for policy_id in preferred_ids if policy_id in allowed_ids]
        if intersection:
            scope = intersection
            meta["phase_repair_mode"] = "preferred_intersection"
        else:
            meta["phase_repair_mode"] = "preferred_no_intersection"
            return chosen_id, meta
    else:
        meta["phase_repair_mode"] = "allowed_scope"

    chosen_bonus = _phase_bonus(policy_catalog.get(chosen_id, []), current_phase)
    if chosen_bonus >= 1:
        return chosen_id, meta

    best = None
    best_bonus = chosen_bonus
    for policy_id in scope:
        if attempts.get(policy_id, 0) >= 3:
            continue
        bonus = _phase_bonus(policy_catalog.get(policy_id, []), current_phase)
        if bonus > best_bonus:
            best_bonus = bonus
            best = policy_id

    meta["phase_repair_attempts_blocked"] = [
        policy_id for policy_id in scope if attempts.get(policy_id, 0) >= 3
    ][:5]

    if best and best_bonus >= 2:
        meta["phase_repair_used"] = True
        meta["phase_repair_to"] = best
        return best, meta

    return chosen_id, meta


def apply_precedence_constraints(
    allowed: list[str],
    precedence: dict | None,
) -> tuple[list[str], dict]:
    prec = precedence or {}
    min_tags = set(prec.get("min_policy_tags") or [])
    block_tags = set(prec.get("block_policy_tags") or [])

    def _tags(policy_id: str) -> set[str]:
        policy = _POLICY_BY_ID.get(policy_id)
        raw = getattr(policy, "tags", None) if policy else None
        return set(raw or set())

    filtered = allowed
    if min_tags:
        filtered = [policy_id for policy_id in filtered if min_tags.issubset(_tags(policy_id))]
    if block_tags:
        filtered = [
            policy_id for policy_id in filtered if _tags(policy_id).isdisjoint(block_tags)
        ]

    meta = {
        "precedence_mode": prec.get("mode"),
        "precedence_reason": prec.get("reason"),
        "precedence_min_tags": sorted(min_tags),
        "precedence_block_tags": sorted(block_tags),
        "precedence_filtered_out": [policy_id for policy_id in allowed if policy_id not in filtered][
            :12
        ],
    }
    return filtered, meta


def _allowed_policy_ids(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
) -> list[str]:
    policy_ids = list_policy_ids()
    if not policy_ids:
        return []

    allowed = set(policy_ids)
    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")

    if health == "tense":
        allowed -= {
            "challenge_anchor_indirect",
            "tradeoff_offer",
            "close_with_conditions",
            "hold_position",
        }
        allowed |= {"deescalate_tension", "rapport_build"}

    required_guards: set[str] = set()
    if health in {"tense", "stalled"}:
        required_guards.add("safe_when_tense")

    def _guard_violation(policy_id: str) -> bool:
        policy = next((item for item in POLICIES if item.policy_id == policy_id), None)
        if not policy or not policy.guards:
            if required_guards:
                return True
            return False
        guards = policy.guards or set()
        if required_guards and not required_guards.issubset(guards):
            return True
        if "requires_price_not_mentioned" in guards and world_state.get("price_mentioned"):
            return True
        return False

    if progress_state.get("turns_in_same_mode", 0) >= 2:
        last_policy = progress_state.get("last_chosen_policy_id", "")
        if last_policy in allowed:
            allowed.remove(last_policy)

    if "stuck_in_policy" in progress_state.get("loop_flags", []):
        last_policy = progress_state.get("last_chosen_policy_id", "")
        if last_policy in allowed:
            allowed.remove(last_policy)

    attempts = progress_state.get("policy_attempts", {})
    outcomes = progress_state.get("policy_last_outcome", {})
    for policy_id, count in attempts.items():
        if count >= 3 and outcomes.get(policy_id) in {"bad", "neutral"}:
            allowed.discard(policy_id)

    allowed = {policy_id for policy_id in allowed if not _guard_violation(policy_id)}

    if not allowed:
        return list_policy_ids()

    return sorted(allowed)


def _required_inputs_met(policy_id: str, world_state: WorldState) -> bool:
    policy = _POLICY_BY_ID.get(policy_id)
    if not policy or not policy.required_inputs:
        return True
    for req in policy.required_inputs:
        key = req.get("key", "")
        op = req.get("op", "exists")
        if op == "exists":
            if key not in world_state:
                return False
        elif op == "true":
            if not bool(world_state.get(key)):
                return False
        elif op == "non_empty":
            value = world_state.get(key)
            if not value:
                return False
            if isinstance(value, (list, dict)) and len(value) == 0:
                return False
    return True


def _violates_hard_constraints(
    policy_id: str,
    world_state: WorldState,
    constraints_struct: dict | None,
) -> bool:
    del policy_id, world_state, constraints_struct
    return False


def allowed_policy_ids(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
) -> list[str]:
    return _allowed_policy_ids(world_state, belief_state, progress_state)


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
