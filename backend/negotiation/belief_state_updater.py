# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import json
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, confloat, conlist

from prompts import BELIEF_UPDATE_SYSTEM_PROMPT, BELIEF_UPDATE_USER_PROMPT
from .schemas import BeliefState, PolicyDecision, WorldState, default_belief_state
from .validation import normalize_belief_state


BELIEF_MODEL = os.getenv("BELIEF_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
BELIEF_TEMPERATURE = float(os.getenv("BELIEF_TEMPERATURE", "0.0"))

_belief_llm = ChatOpenAI(model=BELIEF_MODEL, temperature=BELIEF_TEMPERATURE)

_belief_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", BELIEF_UPDATE_SYSTEM_PROMPT),
        ("user", BELIEF_UPDATE_USER_PROMPT),
    ]
)


class _BeliefReasonModel(BaseModel):
    weight: confloat(ge=0.0, le=1.0) = 0.5
    confidence: confloat(ge=0.0, le=1.0) = 0.5
    evidence: str = ""


class _BeliefStanceModel(BaseModel):
    deal_feasibility: confloat(ge=0.0, le=1.0) = 0.5
    seller_flexibility: confloat(ge=0.0, le=1.0) = 0.5


class _BeliefDynamicsModel(BaseModel):
    interaction_health: str = "stable"
    last_update_evidence: str = ""


class _BeliefToMModel(BaseModel):
    seller_goals: conlist(str, max_items=6) = Field(default_factory=list)
    seller_tactics: conlist(str, max_items=6) = Field(default_factory=list)
    seller_belief_about_me: conlist(str, max_items=6) = Field(default_factory=list)
    confidence: confloat(ge=0.0, le=1.0) = 0.4


class _BeliefStateModel(BaseModel):
    stance: _BeliefStanceModel
    reasons: dict[str, _BeliefReasonModel] = Field(default_factory=dict)
    hypotheses: conlist(str, max_items=5) = Field(default_factory=list)
    dynamics: _BeliefDynamicsModel
    tom: _BeliefToMModel


def update_belief_state(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_decision: PolicyDecision | None,
    last_assistant_message: str,
    user_message: str,
    context_snippet: str,
) -> BeliefState:
    previous = prev_belief_state or default_belief_state()

    messages = _belief_prompt.format_messages(
        prev_belief_state=json.dumps(previous, ensure_ascii=False),
        prev_world_state=json.dumps(prev_world_state, ensure_ascii=False),
        world_state=json.dumps(world_state, ensure_ascii=False),
        world_diff=json.dumps(world_diff, ensure_ascii=False),
        last_policy_decision=json.dumps(last_policy_decision or {}, ensure_ascii=False),
        last_assistant_message=last_assistant_message,
        user_message=user_message,
        recent_history=context_snippet,
    )

    try:
        structured_llm = _belief_llm.with_structured_output(_BeliefStateModel)
        result = structured_llm.invoke(messages)
        data = result.model_dump()
        normalized, issues = normalize_belief_state(data, previous)
        if issues:
            print(f"[belief_state_updater] Validación: {issues}")
        return normalized
    except Exception as exc:
        print(f"[belief_state_updater] Error inesperado: {exc}")

    return previous
