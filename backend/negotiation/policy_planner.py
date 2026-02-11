# backend/negotiation/policy_planner.py
from __future__ import annotations

import os
import warnings

from .elementos.strategy_definitions import PHASE_INDEX

from .policies import POLICIES, list_policy_ids, policy_phase_catalog, safe_neutral_policy_id
from .legacy.intent_constraints import (
    _preferred_policy_ids as _legacy_preferred_policy_ids,
    apply_intent_constraints as _legacy_apply_intent_constraints,
)
from .schemas import BeliefState, IntentHint, NegotiationPhase, ProgressState, WorldState


_POLICY_BY_ID = {policy.policy_id: policy for policy in POLICIES}


def _world_value(world_state: WorldState, key: str) -> object:
    if not isinstance(world_state, dict):
        return None
    universal = world_state.get("universal_domain", {})
    if isinstance(universal, dict) and key in universal:
        return universal.get(key)
    negotiation = world_state.get("negotiation", {})
    if isinstance(negotiation, dict) and key in negotiation:
        return negotiation.get(key)
    return world_state.get(key)


def _world_has_key(world_state: WorldState, key: str) -> bool:
    if not isinstance(world_state, dict):
        return False
    universal = world_state.get("universal_domain", {})
    if isinstance(universal, dict) and key in universal:
        return True
    negotiation = world_state.get("negotiation", {})
    if isinstance(negotiation, dict) and key in negotiation:
        return True
    return key in world_state




def _belief_value(belief_state: BeliefState, key: str):
    cur: object = belief_state
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _required_beliefs_met(policy_id: str, belief_state: BeliefState) -> bool:
    policy = _POLICY_BY_ID.get(policy_id)
    required = list(policy.required_beliefs or []) if policy else []
    if not required:
        return True
    for cond in required:
        key = str(cond.get("key", ""))
        op = str(cond.get("op", "eq"))
        val = cond.get("value")
        cur = _belief_value(belief_state, key)
        if op == "eq" and cur != val:
            return False
        if op == "neq" and cur == val:
            return False
        if op == "gte":
            try:
                if float(cur) < float(val):
                    return False
            except Exception:
                return False
        if op == "lte":
            try:
                if float(cur) > float(val):
                    return False
            except Exception:
                return False
        if op == "in":
            if cur not in (val if isinstance(val, (list, tuple, set)) else [val]):
                return False
    return True
def _phase_bonus(policy_phases: list[str], current_phase: str) -> int:
    if not policy_phases:
        return 0
    if current_phase in policy_phases:
        return 2
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


def _allowed_policy_ids_minimal(
    world_state: WorldState,
    progress_state: ProgressState,
    constraints_struct: dict | None,
) -> list[str]:
    policy_ids = list_policy_ids()
    if not policy_ids:
        return []
    phase_state = progress_state.get("phase_state") or {}
    phase = phase_state.get("phase_effective") or phase_state.get("phase") or "climate"
    recovery_mode = bool(phase_state.get("recovery_mode", False))
    phase_catalog = policy_phase_catalog()
    allowed = [
        policy_id
        for policy_id in policy_ids
        if phase in phase_catalog.get(policy_id, [])
        and _required_inputs_met(policy_id, world_state)
        and not _violates_hard_constraints(policy_id, world_state, constraints_struct)
    ]
    if recovery_mode:
        scoped: list[str] = []
        for policy_id in allowed:
            policy = _POLICY_BY_ID.get(policy_id)
            tags = set(getattr(policy, "tags", set()) or set()) if policy else set()
            guards = set(getattr(policy, "guards", set()) or set()) if policy else set()
            if policy_id == safe_neutral_policy_id() or "recovery_ok" in tags or "safe_when_tense" in guards or "safe_when_tense" in tags:
                if "aggressive" not in tags:
                    scoped.append(policy_id)
        allowed = scoped or [safe_neutral_policy_id()]
    return allowed


def allowed_policy_ids_no_phase(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    constraints_struct: dict | None = None,
) -> list[str]:
    del progress_state
    policy_ids = list_policy_ids()
    if not policy_ids:
        return [safe_neutral_policy_id()]
    allowed = [
        policy_id
        for policy_id in policy_ids
        if _required_inputs_met(policy_id, world_state)
        and not _violates_hard_constraints(policy_id, world_state, constraints_struct)
        and (os.getenv("POLICY_REQUIRED_BELIEFS_ENABLED", "0") != "1" or _required_beliefs_met(policy_id, belief_state))
    ]
    return allowed or [safe_neutral_policy_id()]


def _required_inputs_met(policy_id: str, world_state: WorldState) -> bool:
    policy = _POLICY_BY_ID.get(policy_id)
    if not policy or not policy.required_inputs:
        return True
    for req in policy.required_inputs:
        key = req.get("key", "")
        op = req.get("op", "exists")
        if op == "exists":
            if not _world_has_key(world_state, key):
                return False
        elif op == "true":
            if not bool(_world_value(world_state, key)):
                return False
        elif op == "non_empty":
            value = _world_value(world_state, key)
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
    constraints_struct: dict | None = None,
) -> list[str]:
    base = _allowed_policy_ids_minimal(world_state, progress_state, constraints_struct)
    if os.getenv("POLICY_REQUIRED_BELIEFS_ENABLED", "0") != "1":
        return base
    filtered = [pid for pid in base if _required_beliefs_met(pid, belief_state)]
    return filtered or [safe_neutral_policy_id()]


def _preferred_policy_ids(intent_hint: IntentHint | None) -> list[str]:
    warnings.warn(
        "policy_planner._preferred_policy_ids is deprecated; use legacy.intent_constraints.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _legacy_preferred_policy_ids(intent_hint)


def apply_intent_constraints(
    allowed: list[str],
    intent_hint: IntentHint | None,
) -> tuple[list[str], list[str], dict]:
    warnings.warn(
        "policy_planner.apply_intent_constraints is deprecated; use legacy.intent_constraints.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _legacy_apply_intent_constraints(allowed, intent_hint)
