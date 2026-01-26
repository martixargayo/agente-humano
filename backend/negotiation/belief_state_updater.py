# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import json
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat, conlist, field_validator

from prompts import BELIEF_UPDATE_SYSTEM_PROMPT, BELIEF_UPDATE_USER_PROMPT
from .schemas import BeliefState, PolicyDecision, ReasonKey, WorldState, default_belief_state
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
    model_config = ConfigDict(extra="forbid")
    weight: confloat(ge=0.0, le=1.0) = 0.5
    confidence: confloat(ge=0.0, le=1.0) = 0.5
    evidence: str = ""


class _BeliefStanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deal_feasibility: confloat(ge=0.0, le=1.0) = 0.5
    seller_flexibility: confloat(ge=0.0, le=1.0) = 0.5


class _BeliefDynamicsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interaction_health: Literal["stable", "tense", "stalled"] = "stable"
    last_update_evidence: str = ""


class _BeliefToMModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seller_goals: conlist(str, max_items=6) = Field(default_factory=list)
    seller_tactics: conlist(str, max_items=6) = Field(default_factory=list)
    seller_belief_about_me: conlist(str, max_items=6) = Field(default_factory=list)
    confidence: confloat(ge=0.0, le=1.0) = 0.4


class _BeliefStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stance: _BeliefStanceModel
    reasons: dict[ReasonKey, _BeliefReasonModel] = Field(default_factory=dict)
    hypotheses: conlist(str, max_items=5) = Field(default_factory=list)
    dynamics: _BeliefDynamicsModel
    tom: _BeliefToMModel

    @field_validator("reasons")
    @classmethod
    def _limit_reasons(
        cls, value: dict[ReasonKey, _BeliefReasonModel]
    ) -> dict[ReasonKey, _BeliefReasonModel]:
        if not isinstance(value, dict):
            return {}
        reason_priority = {
            "price_signal": 0,
            "deadline_signal": 1,
            "other_buyer_signal": 2,
            "concession_signal": 3,
            "docs_signal": 4,
            "tone_signal": 5,
        }
        items = sorted(
            value.items(),
            key=lambda kv: (
                -(kv[1].weight * kv[1].confidence),
                reason_priority.get(kv[0], 999),
            ),
        )
        return dict(items[:6])


_EVIDENCE_TRIGGERS = (
    "último",
    "final",
    "hoy",
    "mañana",
    "otro comprador",
    "reservado",
    "me lo quitan",
    "se lo llevan",
    "rebaja",
    "no negocio",
    "innegociable",
)

_CRITICAL_FLAGS = (
    "price_mentioned",
    "deadline_claimed",
    "other_buyer_claimed",
    "docs_claimed",
    "concession_made",
)


def has_belief_evidence_delta(
    world_diff: dict,
    user_message: str,
    prev_world: WorldState,
    world: WorldState,
) -> bool:
    if world_diff:
        return True
    if any(world.get(key) != prev_world.get(key) for key in _CRITICAL_FLAGS):
        return True
    if world.get("tone_signal") != prev_world.get("tone_signal"):
        return True
    prev_hits = set(prev_world.get("tone_marker_hits", []))
    new_hits = set(world.get("tone_marker_hits", [])) - prev_hits
    if new_hits:
        return True
    lower = (user_message or "").lower()
    return any(token in lower for token in _EVIDENCE_TRIGGERS)


def _clamp_step(prev: float, new: float, max_step: float = 0.15) -> float:
    delta = new - prev
    if delta > max_step:
        return prev + max_step
    if delta < -max_step:
        return prev - max_step
    return new


def update_belief_state(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_executed: PolicyDecision | None,
    last_assistant_message: str,
    user_message: str,
    context_snippet: str,
) -> tuple[BeliefState, dict]:
    previous = prev_belief_state or default_belief_state()
    meta = {
        "belief_update_failed": False,
        "belief_update_error": "",
        "belief_update_skipped": False,
    }

    if not has_belief_evidence_delta(world_diff, user_message, prev_world_state, world_state):
        meta["belief_update_skipped"] = True
        return previous, meta

    messages = _belief_prompt.format_messages(
        prev_belief_state=json.dumps(previous, ensure_ascii=False),
        prev_world_state=json.dumps(prev_world_state, ensure_ascii=False),
        world_state=json.dumps(world_state, ensure_ascii=False),
        world_diff=json.dumps(world_diff, ensure_ascii=False),
        last_policy_executed=json.dumps(last_policy_executed or {}, ensure_ascii=False),
        last_assistant_message=last_assistant_message,
        user_message=user_message,
        recent_history=context_snippet,
    )

    try:
        structured_llm = _belief_llm.with_structured_output(_BeliefStateModel)
        result = structured_llm.invoke(messages)
        data = result.model_dump()
        normalized, issues = normalize_belief_state(data, previous)
        normalized["stance"]["deal_feasibility"] = _clamp_step(
            previous["stance"]["deal_feasibility"],
            normalized["stance"]["deal_feasibility"],
            0.15,
        )
        normalized["stance"]["seller_flexibility"] = _clamp_step(
            previous["stance"]["seller_flexibility"],
            normalized["stance"]["seller_flexibility"],
            0.15,
        )
        if issues:
            print(f"[belief_state_updater] Validación: {issues}")
        return normalized, meta
    except Exception as exc:
        print(f"[belief_state_updater] Error inesperado: {exc}")
        meta["belief_update_failed"] = True
        meta["belief_update_error"] = str(exc)

    return previous, meta
