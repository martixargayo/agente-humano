# backend/negotiation/policy_planner.py
from __future__ import annotations

import json
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from prompts import POLICY_PLANNER_SYSTEM_PROMPT, POLICY_PLANNER_USER_PROMPT
from .policies import list_policy_ids, policy_catalog_text
from .schemas import (
    BeliefState,
    PolicyDecision,
    ProgressState,
    WorldState,
    default_policy_decision,
)


PLANNER_MODEL = os.getenv("POLICY_PLANNER_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
PLANNER_TEMPERATURE = float(os.getenv("POLICY_PLANNER_TEMPERATURE", "0.0"))

_planner_llm = ChatOpenAI(model=PLANNER_MODEL, temperature=PLANNER_TEMPERATURE)

_planner_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", POLICY_PLANNER_SYSTEM_PROMPT),
        ("user", POLICY_PLANNER_USER_PROMPT),
    ]
)


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


def plan_policy(
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    objective: str,
    constraints: str,
) -> PolicyDecision:
    policy_ids = list_policy_ids()
    catalog_text = policy_catalog_text()

    messages = _planner_prompt.format_messages(
        policy_catalog=catalog_text,
        policy_ids=policy_ids,
        world_state=json.dumps(world_state, ensure_ascii=False),
        belief_state=json.dumps(belief_state, ensure_ascii=False),
        progress_state=json.dumps(progress_state, ensure_ascii=False),
        objective=objective,
        constraints=constraints,
    )

    result = _planner_llm.invoke(messages)
    raw = (result.content or "").strip()

    try:
        data = json.loads(raw)
        if data.get("policy_id") not in policy_ids:
            raise ValueError("policy_id fuera de catálogo")
        return data  # type: ignore[return-value]
    except Exception as exc:
        print(f"[policy_planner] Output inválido, usando fallback: {exc}")
        return _fallback_policy(belief_state)
