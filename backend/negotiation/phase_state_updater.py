# backend/negotiation/phase_state_updater.py
from __future__ import annotations

import json
import os
from typing import Any, Literal, Tuple

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field, confloat, conlist

from .schemas import (
    BeliefState,
    IntentState,
    NegotiationPhase,
    PhaseState,
    WorldState,
    default_progress_state,
)
from .validation import normalize_phase_state


PHASE_MODEL = os.getenv("PHASE_MODEL_NAME", os.getenv("SUMMARY_MODEL_NAME", "gpt-4o-mini"))
PHASE_TEMPERATURE = float(os.getenv("PHASE_TEMPERATURE", "0.0"))

_phase_llm = ChatOpenAI(model=PHASE_MODEL, temperature=PHASE_TEMPERATURE)


class PhaseSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["world", "belief", "intent", "history"]
    key: str = Field(max_length=48)
    value: str = Field(max_length=120)


class PhaseDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["opening", "discovery", "bargaining", "closing", "recovery"]
    confidence: confloat(ge=0.0, le=1.0) = 0.6
    reasons: conlist(str, max_length=8) = Field(default_factory=list)
    signals: conlist(PhaseSignal, max_length=8) = Field(default_factory=list)
    alternatives: conlist(
        Literal["opening", "discovery", "bargaining", "closing", "recovery"],
        max_length=3,
    ) = Field(default_factory=list)


PHASE_UPDATE_SYSTEM_PROMPT = """
Eres un clasificador de fase para una negociación.
Devuelves SOLO JSON válido que cumpla el schema.

Reglas estrictas:
- "phase" ∈ {opening, discovery, bargaining, closing, recovery}
- "reasons" deben ser etiquetas normalizadas, con prefijo:
  - world:<flag> | belief:<flag> | intent:<flag> | history:<flag>
  Ej: "world:price_firm", "belief:health_tense"
- "signals": lista corta de señales observables (no inventes).
- Si es ambiguo, confidence baja y lista alternatives.
- NO texto fuera del JSON, NO markdown.
""".strip()

PHASE_UPDATE_USER_PROMPT = """
[Prev PhaseState]
{prev_phase_state}

[WorldState]
{world_state}

[World diff]
{world_diff}

[BeliefState dynamics + stance]
{belief_compact}

[IntentState compact]
{intent_compact}

[Recent history (max 8 turns, may be empty)]
{recent_history}

Devuelve SOLO JSON del PhaseDecisionModel.
""".strip()

_phase_prompt = ChatPromptTemplate.from_messages(
    [("system", PHASE_UPDATE_SYSTEM_PROMPT), ("user", PHASE_UPDATE_USER_PROMPT)]
)

_REASON_PREFIXES = {"world", "belief", "intent", "history"}
_PHASE_ORDER: list[NegotiationPhase] = ["opening", "discovery", "bargaining", "closing"]
_PHASE_INDEX = {phase: idx for idx, phase in enumerate(_PHASE_ORDER)}


def _compact_belief(belief: BeliefState) -> dict:
    dyn = (belief.get("dynamics") or {})
    stance = (belief.get("stance") or {})
    return {
        "interaction_health": dyn.get("interaction_health", "stable"),
        "deal_feasibility": stance.get("deal_feasibility", 0.5),
        "seller_flexibility": stance.get("seller_flexibility", 0.5),
    }


def _compact_intent(intent: IntentState | None) -> dict:
    if not intent:
        return {}
    steps = intent.get("steps") or [{}]
    idx = intent.get("step_idx", 0) or 0
    step = steps[idx] if idx < len(steps) else {}
    return {
        "status": intent.get("status", ""),
        "intent_type": intent.get("intent_type", ""),
        "step_kind": step.get("kind", ""),
        "target_slot": step.get("target_slot", ""),
    }


def _strong_phase_signals(
    world_diff: dict,
    belief: BeliefState,
    intent: IntentState | None,
) -> bool:
    if world_diff:
        return True
    health = (belief.get("dynamics") or {}).get("interaction_health", "stable")
    if health in {"tense", "stalled"}:
        return True
    if intent and intent.get("status") == "active" and intent.get("intent_type") in {
        "closing",
        "concession",
    }:
        return True
    return False


def _should_update_phase(
    prev_phase: PhaseState,
    world_diff: dict,
    belief: BeliefState,
    intent: IntentState | None,
    turn_count: int,
) -> Tuple[bool, str]:
    last = int(prev_phase.get("last_updated_turn", 0) or 0)
    interval = int(os.getenv("PHASE_UPDATE_MIN_INTERVAL_TURNS", "2"))
    if _strong_phase_signals(world_diff, belief, intent):
        return True, "strong_signals"
    if (turn_count - last) >= interval:
        return True, "budget_interval"
    return False, "budget_hold"


def _hard_phase_override(
    world: WorldState,
    belief: BeliefState,
    intent: IntentState | None,
) -> tuple[NegotiationPhase | None, list[str]]:
    reasons: list[str] = []
    health = (belief.get("dynamics") or {}).get("interaction_health", "stable")
    if health in {"tense", "stalled"}:
        reasons.append(f"belief:health_{health}")
        return "recovery", reasons

    if intent and intent.get("intent_type") == "closing":
        reasons.append("intent:intent_type_closing")
        return "closing", reasons

    if world.get("price_firm") is True:
        reasons.append("world:price_firm")
        return "closing", reasons

    if world.get("price_mentioned") and (
        world.get("concession_made")
        or (intent and intent.get("intent_type") == "concession")
    ):
        reasons.append("world:price_mentioned")
        reasons.append(
            "world:concession_made"
            if world.get("concession_made")
            else "intent:intent_type_concession"
        )
        return "bargaining", reasons

    if (
        intent
        and intent.get("intent_type") in {"info_extract", "credibility_check"}
    ) or world.get("docs_claimed") or world.get("other_buyer_claimed"):
        reasons.append(
            "intent:intent_type_info_extract"
            if intent and intent.get("intent_type") == "info_extract"
            else "world:credibility_signal"
        )
        return "discovery", reasons

    return None, []


def _transition_threshold(prev: NegotiationPhase, new: NegotiationPhase) -> float:
    if prev == new:
        return 0.0
    if prev == "recovery" or new == "recovery":
        return 0.55
    if prev in _PHASE_INDEX and new in _PHASE_INDEX:
        dist = abs(_PHASE_INDEX[new] - _PHASE_INDEX[prev])
        return 0.62 if dist == 1 else 0.72
    return 0.70


def _normalize_reasons(reasons: list[Any]) -> list[str]:
    normalized: list[str] = []
    for reason in reasons:
        raw = str(reason).strip()
        if not raw:
            continue
        if ":" in raw:
            prefix, rest = raw.split(":", 1)
            if prefix in _REASON_PREFIXES and rest:
                normalized.append(f"{prefix}:{rest.strip()}"[:64])
                continue
        key = raw.replace(" ", "_")[:48] or "unspecified"
        normalized.append(f"history:{key}"[:64])
    return normalized[:8]


def _normalize_signals(signals: list[Any]) -> list[dict]:
    out: list[dict] = []
    for signal in signals or []:
        if not isinstance(signal, dict):
            continue
        source = str(signal.get("source", "")).strip()
        if source not in {"world", "belief", "intent", "history"}:
            continue
        key = str(signal.get("key", "")).strip()[:48]
        val = str(signal.get("value", "")).strip()[:120]
        if not key or not val:
            continue
        out.append({"source": source, "key": key, "value": val})
        if len(out) >= 8:
            break
    return out


def _truncate_history(text: str, max_chars: int = 1200) -> str:
    trimmed = (text or "").strip()
    if len(trimmed) <= max_chars:
        return trimmed
    return trimmed[-max_chars:]


def _apply_hysteresis(
    prev_state: PhaseState,
    proposed: dict,
    turn_count: int,
) -> tuple[PhaseState, dict]:
    prev_phase: NegotiationPhase = prev_state.get("phase", "opening")
    prev_conf = float(prev_state.get("confidence", 0.6) or 0.6)
    new_phase = proposed.get("phase", prev_phase)
    new_conf = float(proposed.get("confidence", prev_conf) or prev_conf)

    threshold = _transition_threshold(prev_phase, new_phase)
    meta = {
        "threshold": threshold,
        "attempted_change": new_phase != prev_phase,
        "held": False,
    }
    if new_phase != prev_phase and new_conf < threshold:
        proposed["phase"] = prev_phase
        proposed["confidence"] = max(prev_conf, new_conf) * 0.97
        reasons = list(proposed.get("reasons") or [])
        proposed["reasons"] = (["history:hysteresis_hold"] + reasons)[:8]
        meta["held"] = True

    proposed["last_updated_turn"] = turn_count
    normalized, _ = normalize_phase_state(proposed)
    return normalized, meta


def _apply_precedence(
    normalized: PhaseState,
    meta: dict,
    phase_floor: str | None,
    allow_closing: bool,
) -> PhaseState:
    if phase_floor and normalized.get("phase") != phase_floor:
        meta["phase_precedence_forced"] = True
        normalized["phase"] = phase_floor
        normalized["reasons"] = (["precedence:phase_floor"] + normalized.get("reasons", []))[:8]

    if not allow_closing and normalized.get("phase") == "closing":
        meta["phase_precedence_blocked_closing"] = True
        normalized["phase"] = "bargaining"
        normalized["reasons"] = (
            ["precedence:block_closing"] + normalized.get("reasons", [])
        )[:8]
    return normalized


def _sync_phase_meta(meta: dict, normalized: PhaseState) -> None:
    meta["phase_after"] = normalized.get("phase", "opening")
    meta["phase_confidence_after"] = float(normalized.get("confidence", 0.6) or 0.6)
    meta["phase_changed"] = meta.get("phase_before") != meta["phase_after"]


def update_phase_state(
    prev_phase_state: PhaseState | None,
    world_state: WorldState,
    world_diff: dict,
    belief_state: BeliefState,
    intent_state: IntentState | None,
    recent_history_text: str,
    turn_count: int,
    precedence: dict | None,
) -> tuple[PhaseState, dict]:
    prev = prev_phase_state or default_progress_state()["phase_state"]
    history_text = recent_history_text or ""
    truncated_history = _truncate_history(history_text)
    prec = precedence or {}
    phase_floor = prec.get("phase_floor")
    allow_closing = prec.get("allow_closing", True)
    meta: dict = {
        "phase_update_used": False,
        "phase_update_reason": "",
        "phase_update_failed": False,
        "phase_changed": False,
        "phase_before": prev.get("phase", "opening"),
        "phase_after": prev.get("phase", "opening"),
        "phase_confidence_before": float(prev.get("confidence", 0.6) or 0.6),
        "phase_confidence_after": float(prev.get("confidence", 0.6) or 0.6),
        "phase_hard_override_used": False,
        "phase_llm_confidence": None,
        "phase_llm_phase_proposed": None,
        "phase_transition_attempted": False,
        "phase_threshold_used": None,
        "phase_hysteresis_held": False,
        "phase_history_chars": len(history_text),
        "phase_history_chars_used": len(truncated_history),
    }

    forced, forced_reasons = _hard_phase_override(
        world_state, belief_state, intent_state
    )
    if forced is not None:
        proposed = dict(prev)
        proposed["phase"] = forced
        floor = 0.85
        if forced == "recovery":
            floor = 0.90
        proposed["confidence"] = max(float(prev.get("confidence", 0.6) or 0.6), floor)
        proposed["reasons"] = (forced_reasons + ["history:hard_override"])[:8]
        proposed["last_updated_turn"] = turn_count
        normalized, issues = normalize_phase_state(proposed)
        meta["phase_hard_override_used"] = True
        meta["phase_update_reason"] = "hard_override"
        meta["phase_update_used"] = False
        meta["phase_issues"] = issues
        meta["phase_llm_confidence"] = None
        meta["phase_threshold_used"] = None
        meta["phase_hysteresis_held"] = False
        normalized = _apply_precedence(normalized, meta, phase_floor, allow_closing)
        _sync_phase_meta(meta, normalized)
        meta["phase_transition_attempted"] = (
            meta["phase_before"] != meta["phase_after"]
        )
        return normalized, meta

    should, why = _should_update_phase(
        prev, world_diff, belief_state, intent_state, turn_count
    )
    meta["phase_update_reason"] = why
    if not should:
        normalized = prev
        normalized = _apply_precedence(normalized, meta, phase_floor, allow_closing)
        _sync_phase_meta(meta, normalized)
        return normalized, meta

    messages = _phase_prompt.format_messages(
        prev_phase_state=json.dumps(prev, ensure_ascii=False),
        world_state=json.dumps(world_state, ensure_ascii=False),
        world_diff=json.dumps(world_diff, ensure_ascii=False),
        belief_compact=json.dumps(_compact_belief(belief_state), ensure_ascii=False),
        intent_compact=json.dumps(_compact_intent(intent_state), ensure_ascii=False),
        recent_history=truncated_history,
    )

    try:
        structured = _phase_llm.with_structured_output(PhaseDecisionModel)
        result = structured.invoke(messages)
        proposed = result.model_dump()
        meta["phase_update_used"] = True
        meta["phase_llm_phase_proposed"] = proposed.get("phase")
        meta["phase_llm_confidence"] = float(proposed.get("confidence", 0.0) or 0.0)

        proposed["reasons"] = _normalize_reasons(proposed.get("reasons") or [])
        proposed["signals"] = _normalize_signals(proposed.get("signals") or [])

        normalized, hyst = _apply_hysteresis(prev, proposed, turn_count)
        meta["phase_threshold_used"] = hyst["threshold"]
        meta["phase_transition_attempted"] = hyst["attempted_change"]
        meta["phase_hysteresis_held"] = hyst["held"]
        normalized = _apply_precedence(normalized, meta, phase_floor, allow_closing)
        _sync_phase_meta(meta, normalized)
        return normalized, meta
    except Exception as exc:
        meta["phase_update_failed"] = True
        meta["phase_update_error"] = str(exc)
        normalized = prev
        normalized = _apply_precedence(normalized, meta, phase_floor, allow_closing)
        _sync_phase_meta(meta, normalized)
        return normalized, meta


def postprocess_phase_candidate(
    prev_phase_state: PhaseState | None,
    phase_candidate: dict,
    turn_count: int,
    precedence: dict | None,
) -> tuple[PhaseState, dict]:
    prev = prev_phase_state or default_progress_state()["phase_state"]
    prec = precedence or {}
    phase_floor = prec.get("phase_floor")
    allow_closing = prec.get("allow_closing", True)
    meta = {
        "phase_update_used": True,
        "phase_update_reason": "planner",
        "phase_update_failed": False,
        "phase_changed": False,
        "phase_before": prev.get("phase", "opening"),
        "phase_after": prev.get("phase", "opening"),
        "phase_confidence_before": float(prev.get("confidence", 0.6) or 0.6),
        "phase_confidence_after": float(prev.get("confidence", 0.6) or 0.6),
        "phase_hard_override_used": False,
        "phase_llm_confidence": float(phase_candidate.get("confidence", 0.0) or 0.0),
        "phase_llm_phase_proposed": phase_candidate.get("phase"),
        "phase_transition_attempted": False,
        "phase_threshold_used": None,
        "phase_hysteresis_held": False,
    }
    normalized, hyst = _apply_hysteresis(prev, phase_candidate, turn_count)
    meta["phase_threshold_used"] = hyst["threshold"]
    meta["phase_transition_attempted"] = hyst["attempted_change"]
    meta["phase_hysteresis_held"] = hyst["held"]
    normalized = _apply_precedence(normalized, meta, phase_floor, allow_closing)
    _sync_phase_meta(meta, normalized)
    return normalized, meta
