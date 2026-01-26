# backend/negotiation/policy_planner.py
from __future__ import annotations

import json
import os
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from prompts import POLICY_PLANNER_SYSTEM_PROMPT, POLICY_PLANNER_USER_PROMPT
from .policies import list_policy_ids, policy_catalog_text
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
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
    policy_id: str = ""
    reason: str = ""
    micro_goal: str = ""
    risk_posture: Literal["low", "mid", "high"] = Field(default="low")


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
    allowed = set(list_policy_ids())
    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")

    if health == "tense":
        allowed -= {
            "challenge_anchor_indirect",
            "tradeoff_offer",
            "close_with_conditions",
            "hold_position",
        }
        allowed |= {"deescalate_tension", "rapport_build"}

    if progress_state.get("turns_in_same_mode", 0) >= 2:
        last_policy = progress_state.get("last_policy_id", "")
        if last_policy in allowed:
            allowed.remove(last_policy)

    if "stuck_in_policy" in progress_state.get("loop_flags", []):
        last_policy = progress_state.get("last_policy_id", "")
        if last_policy in allowed:
            allowed.remove(last_policy)

    attempts = progress_state.get("policy_attempts", {})
    last_outcome = progress_state.get("last_policy_outcome", "")
    for policy_id, count in attempts.items():
        if count >= 3 and last_outcome in {"bad", "neutral"}:
            allowed.discard(policy_id)

    if world_state.get("price_mentioned"):
        allowed.discard("delay_price_discussion")

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


def plan_policy(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    objective: str,
    constraints: str,
    recent_context: str,
) -> tuple[PolicyDecision, dict]:
    catalog_text = policy_catalog_text()
    allowed = _allowed_policy_ids(world_state, belief_state, progress_state)
    meta = {
        "planner_failed": False,
        "planner_error": "",
        "planner_fallback_used": False,
        "policy_normalization_changed": False,
        "issues": [],
    }

    messages = _planner_prompt.format_messages(
        policy_catalog=catalog_text,
        world_state=json.dumps(world_state, ensure_ascii=False),
        belief_state=json.dumps(belief_state, ensure_ascii=False),
        progress_state=json.dumps(progress_state, ensure_ascii=False),
        recent_context=recent_context,
        objective=objective,
        constraints=constraints,
        allowed_policy_ids=allowed,
    )

    try:
        structured_llm = _planner_llm.with_structured_output(_PolicyDecisionModel)
        result = structured_llm.invoke(messages)
        data = result.model_dump()
        normalized, issues = normalize_policy_decision(data, allowed)
        meta["issues"] = issues
        meta["policy_normalization_changed"] = any(
            normalized.get(key) != data.get(key)
            for key in ("policy_id", "reason", "micro_goal", "risk_posture")
        )
        if issues:
            print(f"[policy_planner] Validación: {issues}")
        if issues or normalized["policy_id"] not in allowed:
            meta["planner_fallback_used"] = True
            return _fallback_policy(belief_state), meta
        normalized["micro_goal"] = _repair_micro_goal(
            normalized["policy_id"], normalized["micro_goal"]
        )
        if _violates_constraints(normalized["micro_goal"], constraints):
            print("[policy_planner] Micro-objetivo viola constraints, reparando.")
            normalized["micro_goal"] = "Mantener confidencial el límite y avanzar con cautela."
        return normalized, meta
    except Exception as exc:
        print(f"[policy_planner] Output inválido, usando fallback: {exc}")
        meta["planner_failed"] = True
        meta["planner_error"] = str(exc)
        meta["planner_fallback_used"] = True
        return _fallback_policy(belief_state), meta
