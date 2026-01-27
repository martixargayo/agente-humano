# backend/negotiation/policy_planner.py
from __future__ import annotations

import json
import os
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from prompts import POLICY_PLANNER_SYSTEM_PROMPT, POLICY_PLANNER_USER_PROMPT
from .policies import POLICIES, list_policy_ids, policy_catalog_text
from .schemas import (
    BeliefState,
    IntentHint,
    NegotiationPhase,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_policy_decision,
)
from .validation import normalize_policy_decision


PLANNER_MODEL = os.getenv("POLICY_PLANNER_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
PLANNER_TEMPERATURE = float(os.getenv("POLICY_PLANNER_TEMPERATURE", "0.0"))

_planner_llm = ChatOpenAI(model=PLANNER_MODEL, temperature=PLANNER_TEMPERATURE)

_planner_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", POLICY_PLANNER_SYSTEM_PROMPT),
        ("user", POLICY_PLANNER_USER_PROMPT),
    ]
)


class _PolicyDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: str = ""
    reason: str = Field(default="", max_length=180)
    micro_goal: str = Field(default="", max_length=140)
    risk_posture: Literal["low", "mid", "high"] = Field(default="low")


_PHASE_ORDER: list[NegotiationPhase] = ["opening", "discovery", "bargaining", "closing"]
_PHASE_INDEX: dict[NegotiationPhase, int] = {phase: idx for idx, phase in enumerate(_PHASE_ORDER)}
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
    if current_phase in _PHASE_INDEX:
        cur_i = _PHASE_INDEX[current_phase]  # type: ignore[index]
        for phase in policy_phases:
            if phase in _PHASE_INDEX and abs(_PHASE_INDEX[phase] - cur_i) == 1:
                return 1
    return 0


def _phase_candidates(
    allowed_ids: list[str],
    current_phase: str,
    limit: int = 5,
) -> list[dict]:
    candidates: list[dict] = []
    for policy_id in allowed_ids:
        policy = _POLICY_BY_ID.get(policy_id)
        policy_phases = policy.phase_hints if policy else []
        candidates.append(
            {
                "policy_id": policy_id,
                "phase_bonus": _phase_bonus(policy_phases, current_phase),
                "phase_hints": policy_phases,
            }
        )
    candidates.sort(
        key=lambda item: (-(item["phase_bonus"]), item["policy_id"])
    )
    return candidates[:limit]


def repair_policy_by_phase(
    chosen_id: str,
    allowed_ids: list[str],
    policy_catalog: dict[str, list[str]],
    current_phase: str,
) -> tuple[str, dict]:
    meta = {
        "phase_repair_used": False,
        "phase_repair_from": chosen_id,
        "phase_repair_to": chosen_id,
    }
    chosen_bonus = _phase_bonus(policy_catalog.get(chosen_id, []), current_phase)
    if chosen_bonus >= 1:
        return chosen_id, meta

    best = None
    for policy_id in allowed_ids:
        bonus = _phase_bonus(policy_catalog.get(policy_id, []), current_phase)
        if bonus >= 2:
            best = policy_id
            break

    if best:
        meta["phase_repair_used"] = True
        meta["phase_repair_to"] = best
        return best, meta

    return chosen_id, meta


def _fallback_policy(belief_state: BeliefState) -> PolicyDecision:
    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")
    if health == "tense":
        return {
            "policy_id": "deescalate_tension",
            "reason": "Interacción tensa: primero bajar presión.",
            "micro_goal": "Reducir tensión y mantener conversación abierta.",
            "risk_posture": "low",
        }
    return {
        "policy_id": "info_extract_critical",
        "reason": "Fallback informativo para obtener datos faltantes.",
        "micro_goal": "Conseguir detalles críticos sin abrir precio.",
        "risk_posture": "low",
    }


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


def allowed_policy_ids(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
) -> list[str]:
    return _allowed_policy_ids(world_state, belief_state, progress_state)


def _repair_micro_goal(policy_id: str, micro_goal: str) -> str:
    if policy_id == "delay_price_discussion":
        forbidden = ["precio", "€", "euros", "cifra", "10.000", "10000"]
        if any(term in micro_goal.lower() for term in forbidden):
            return "Desviar la conversación hacia información técnica sin entrar en cifras."
    return micro_goal


def _violates_constraints(micro_goal: str, constraints: str) -> bool:
    if "Evitar revelar" in constraints or "no revelar" in constraints.lower():
        lowered = micro_goal.lower()
        if "10.000" in lowered or "10000" in lowered or "límite" in lowered:
            return True
    return False


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
                (policy := next((item for item in POLICIES if item.policy_id == policy_id), None))
                and policy.guards
                and "requires_slot_complete" in policy.guards
            )
        ]
    commitment = intent_hint.get("commitment_level")
    if commitment == "hard" and preferred:
        forced = [policy_id for policy_id in preferred if policy_id in allowed]
        if forced:
            meta["planner_mode"] = "intent_forced"
            return forced, preferred, meta
        meta["planner_error"] = "intent_policy_unavailable"
        meta["planner_fallback_used"] = True
        return allowed, preferred, meta
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


def plan_policy(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    intent_hint: dict | None,
    objective: str,
    constraints: str,
    recent_context: str,
) -> tuple[PolicyDecision, dict]:
    policy_ids = list_policy_ids()
    allowed = _allowed_policy_ids(world_state, belief_state, progress_state)
    allowed, preferred, intent_meta = apply_intent_constraints(allowed, intent_hint)
    current_phase = (progress_state.get("phase_state") or {}).get("phase", "opening")
    phase_catalog = {policy.policy_id: policy.phase_hints for policy in POLICIES}
    meta = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "issues": [],
        "planner_mode": intent_meta.get("planner_mode", ""),
        "intent_preferred_policy_ids": preferred,
        "allowed_policy_ids": allowed,
        "current_phase": current_phase,
        "phase_candidates": _phase_candidates(allowed, current_phase),
    }

    def _apply_phase_bias(decision: PolicyDecision) -> PolicyDecision:
        decision_id, repair_meta = repair_policy_by_phase(
            decision.get("policy_id", ""),
            allowed,
            phase_catalog,
            current_phase,
        )
        if decision_id and decision_id != decision.get("policy_id"):
            decision["policy_id"] = decision_id
        meta.update(repair_meta)
        meta["phase_bonus"] = _phase_bonus(
            phase_catalog.get(decision.get("policy_id", ""), []),
            current_phase,
        )
        return decision

    if not policy_ids:
        meta["planner_failed"] = True
        meta["planner_error"] = "policy_catalog_empty"
        meta["planner_fallback_used"] = True
        meta["issues"].append("policy_catalog_empty")
        return _apply_phase_bias(default_policy_decision()), meta

    if intent_meta.get("planner_error"):
        meta["planner_failed"] = True
        meta["planner_error"] = intent_meta["planner_error"]
        meta["planner_fallback_used"] = True
        meta["issues"].append(intent_meta["planner_error"])
        return _apply_phase_bias(_fallback_policy(belief_state)), meta

    if not allowed:
        meta["planner_failed"] = True
        meta["planner_error"] = "allowed_empty"
        meta["planner_fallback_used"] = True
        meta["issues"].append("allowed_empty")
        return _apply_phase_bias(default_policy_decision()), meta

    catalog_text = policy_catalog_text()
    messages = _planner_prompt.format_messages(
        policy_catalog=catalog_text,
        world_state=json.dumps(world_state, ensure_ascii=False),
        belief_state=json.dumps(belief_state, ensure_ascii=False),
        progress_state=json.dumps(progress_state, ensure_ascii=False),
        recent_context=recent_context,
        objective=objective,
        constraints=constraints,
        allowed_policy_ids=allowed,
        intent_hint=json.dumps(intent_hint or {}, ensure_ascii=False),
        preferred_policy_ids=preferred,
    )

    try:
        structured_llm = _planner_llm.with_structured_output(_PolicyDecisionModel)
        result = structured_llm.invoke(messages)
        data = result.model_dump()
        normalized, issues = normalize_policy_decision(data, allowed)
        meta["issues"] = issues
        meta["policy_normalization_changed"] = bool(issues)
        if issues:
            print(f"[policy_planner] Validación: {issues}")
        if issues or normalized["policy_id"] not in allowed:
            meta["planner_fallback_used"] = True
            return _apply_phase_bias(_fallback_policy(belief_state)), meta
        normalized["micro_goal"] = _repair_micro_goal(
            normalized["policy_id"], normalized["micro_goal"]
        )
        if _violates_constraints(normalized["micro_goal"], constraints):
            print("[policy_planner] Micro-objetivo viola constraints, reparando.")
            normalized["micro_goal"] = "Mantener confidencial el límite y avanzar con cautela."
        return _apply_phase_bias(normalized), meta
    except Exception as exc:
        print(f"[policy_planner] Output inválido, usando fallback: {exc}")
        meta["planner_failed"] = True
        meta["planner_error"] = str(exc)
        meta["planner_fallback_used"] = True
        return _apply_phase_bias(_fallback_policy(belief_state)), meta
