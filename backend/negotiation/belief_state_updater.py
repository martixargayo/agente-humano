# backend/negotiation/belief_state_updater.py
from __future__ import annotations

import json
import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat, conlist, field_validator

from prompts import (
    BELIEF_UPDATE_SYSTEM_PROMPT,
    BELIEF_UPDATE_USER_PROMPT,
    PHASE_UPDATE_SYSTEM_PROMPT,
    PHASE_UPDATE_USER_PROMPT,
)
from .schemas import (
    BeliefState,
    IntentState,
    PhaseState,
    PolicyDecision,
    ReasonKey,
    WorldState,
    default_belief_state,
    default_progress_state,
)
from .validation import normalize_belief_state, normalize_phase_state


BELIEF_MODEL = os.getenv("BELIEF_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
BELIEF_TEMPERATURE = float(os.getenv("BELIEF_TEMPERATURE", "0.0"))

_belief_llm = ChatOpenAI(model=BELIEF_MODEL, temperature=BELIEF_TEMPERATURE)

_belief_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", BELIEF_UPDATE_SYSTEM_PROMPT),
        ("user", BELIEF_UPDATE_USER_PROMPT),
    ]
)

_phase_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", PHASE_UPDATE_SYSTEM_PROMPT),
        ("user", PHASE_UPDATE_USER_PROMPT),
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
    seller_goals: conlist(str, max_length=6) = Field(default_factory=list)
    seller_tactics: conlist(str, max_length=6) = Field(default_factory=list)
    seller_belief_about_me: conlist(str, max_length=6) = Field(default_factory=list)
    confidence: confloat(ge=0.0, le=1.0) = 0.4


class _BeliefStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stance: _BeliefStanceModel
    reasons: dict[ReasonKey, _BeliefReasonModel] = Field(default_factory=dict)
    hypotheses: conlist(str, max_length=5) = Field(default_factory=list)
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
                reason_priority.get(str(kv[0]), 999),
                str(kv[0]),
            ),
        )
        return dict(items[:6])


class _PhaseDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["opening", "discovery", "bargaining", "closing", "recovery"]
    confidence: confloat(ge=0.0, le=1.0) = 0.6
    reasons: conlist(str, max_length=8) = Field(default_factory=list)
    alternatives: conlist(
        Literal["opening", "discovery", "bargaining", "closing", "recovery"],
        max_length=3,
    ) = Field(default_factory=list)


_CRITICAL_FLAGS = (
    "price_mentioned",
    "deadline_claimed",
    "other_buyer_claimed",
    "docs_claimed",
    "concession_made",
    "message_is_vague",
    "batna_claimed",
    "urgency_claimed",
    "min_price_claimed",
    "price_firm",
    "evidence_offered",
)


def has_belief_evidence_delta(
    world_diff: dict,
    prev_world: WorldState,
    world: WorldState,
    extractor_meta: dict | None = None,
) -> bool:
    """
    Gate determinista para decidir si vale la pena ejecutar belief updater (coste alto).
    P0.1: NO dependemos del texto del usuario.
    """
    decisions = (extractor_meta or {}).get("decisions", {}) or {}
    if decisions.get("should_update_beliefs") is True:
        return True
    if world_diff:
        return True
    for key in _CRITICAL_FLAGS:
        if world.get(key) != prev_world.get(key):
            return True
    if world.get("tone_signal") != prev_world.get("tone_signal"):
        return True
    prev_hits = set(prev_world.get("tone_marker_hits", []) or [])
    new_hits = set(world.get("tone_marker_hits", []) or []) - prev_hits
    if new_hits:
        return True
    return False


def _clamp_step(prev: float, new: float, max_step: float = 0.15) -> float:
    delta = new - prev
    if delta > max_step:
        return prev + max_step
    if delta < -max_step:
        return prev - max_step
    return new


def _apply_phase_hysteresis(
    prev_phase_state: PhaseState,
    proposed: dict,
    turn_count: int,
) -> PhaseState:
    prev_phase = prev_phase_state.get("phase", "opening")
    prev_conf = float(prev_phase_state.get("confidence", 0.6))
    new_phase = proposed.get("phase", prev_phase)
    new_conf = float(proposed.get("confidence", prev_conf))

    if new_phase != prev_phase and new_conf < 0.75:
        proposed["phase"] = prev_phase
        proposed["confidence"] = max(prev_conf, new_conf) * 0.95
        reasons = proposed.get("reasons") or []
        proposed["reasons"] = ["hysteresis_hold"] + reasons[:7]

    proposed["last_updated_turn"] = turn_count
    normalized, _issues = normalize_phase_state(proposed)
    return normalized


def _update_phase_state_llm(
    prev_phase_state: PhaseState,
    world_state: WorldState,
    world_diff: dict,
    belief_state: BeliefState,
    intent_state: IntentState | None,
    recent_history_text: str,
    turn_count: int,
) -> tuple[PhaseState, dict]:
    meta = {"phase_update_used": False, "phase_update_reason": "", "phase_update_failed": False}
    strong = bool(world_diff) or belief_state.get("dynamics", {}).get("interaction_health") in {
        "tense",
        "stalled",
    }
    if not strong and (turn_count - int(prev_phase_state.get("last_updated_turn", 0)) < 2):
        meta["phase_update_reason"] = "phase_skip_budget"
        return prev_phase_state, meta

    messages = _phase_prompt.format_messages(
        prev_phase_state=json.dumps(prev_phase_state, ensure_ascii=False),
        world_state=json.dumps(world_state, ensure_ascii=False),
        world_diff=json.dumps(world_diff, ensure_ascii=False),
        belief_state=json.dumps(belief_state, ensure_ascii=False),
        intent_state=json.dumps(intent_state or {}, ensure_ascii=False),
        recent_history=recent_history_text,
    )

    try:
        structured_llm = _belief_llm.with_structured_output(_PhaseDecisionModel)
        result = structured_llm.invoke(messages)
        proposed = result.model_dump()
        meta["phase_update_used"] = True
        return _apply_phase_hysteresis(prev_phase_state, proposed, turn_count), meta
    except Exception as exc:
        meta["phase_update_failed"] = True
        meta["phase_update_error"] = str(exc)
        return prev_phase_state, meta


def update_belief_state(
    prev_belief_state: BeliefState | None,
    prev_world_state: WorldState,
    world_state: WorldState,
    world_diff: dict,
    last_policy_executed: PolicyDecision | None,
    last_assistant_message: str,
    user_message: str,
    context_snippet: str,
    prev_phase_state: PhaseState | None = None,
    intent_state: IntentState | None = None,
    recent_history_text: str | None = None,
    turn_count: int = 0,
    extractor_meta: dict | None = None,
) -> tuple[BeliefState, dict]:
    previous = prev_belief_state or default_belief_state()
    meta = {
        "belief_update_failed": False,
        "belief_update_error": "",
        "belief_update_skipped": False,
    }

    if not has_belief_evidence_delta(
        world_diff=world_diff,
        prev_world=prev_world_state,
        world=world_state,
        extractor_meta=extractor_meta,
    ):
        meta["belief_update_skipped"] = True
        phase_state, phase_meta = _update_phase_state_llm(
            prev_phase_state or default_progress_state()["phase_state"],
            world_state,
            world_diff,
            previous,
            intent_state,
            recent_history_text or context_snippet,
            turn_count,
        )
        meta["phase_state"] = phase_state
        meta["phase_meta"] = phase_meta
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
        phase_state, phase_meta = _update_phase_state_llm(
            prev_phase_state or default_progress_state()["phase_state"],
            world_state,
            world_diff,
            normalized,
            intent_state,
            recent_history_text or context_snippet,
            turn_count,
        )
        meta["phase_state"] = phase_state
        meta["phase_meta"] = phase_meta
        return normalized, meta
    except Exception as exc:
        print(f"[belief_state_updater] Error inesperado: {exc}")
        meta["belief_update_failed"] = True
        meta["belief_update_error"] = str(exc)

    phase_state, phase_meta = _update_phase_state_llm(
        prev_phase_state or default_progress_state()["phase_state"],
        world_state,
        world_diff,
        previous,
        intent_state,
        recent_history_text or context_snippet,
        turn_count,
    )
    meta["phase_state"] = phase_state
    meta["phase_meta"] = phase_meta
    return previous, meta
