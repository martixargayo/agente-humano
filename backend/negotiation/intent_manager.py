from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import List, Tuple

from .elementos.strategy_definitions import (
    INTENT_CLOSE_STEP,
    INTENT_CONTRACTS,
    INTENT_CONFIDENCE_DECAY,
    INTENT_COST_REPEAT,
    INTENT_COST_TENSION,
    INTENT_COST_URGENCY,
    INTENT_FIRMNESS_REPLAN_THRESHOLD,
    INTENT_MAX_ATTEMPTS_PER_STEP,
    INTENT_MAX_TURNS,
    INTENT_NO_PROGRESS_ABORT_TURNS,
    INTENT_START_UTILITY_THRESHOLD,
    INTENT_STEP_SEQUENCE,
    INTENT_WEIGHT_OPEN_FACTORS,
    INTENT_WEIGHT_SLOTS,
    INTENT_WEIGHT_UNCERTAINTY,
    KNOWN_SUCCESS_CRITERIA,
    OPEN_FACTOR_SIGNALS,
    PIVOT_KIND_MAPPING,
    URGENCY_DEADLINE_DAYS,
)
from .schemas import (
    BeliefState,
    IntentHint,
    IntentState,
    IntentStep,
    ProgressState,
    StepKind,
    WorldState,
    default_intent_state,
)


@dataclass(frozen=True)
class MultiTurnScore:
    should_start: bool
    score: int
    reasons: List[str]


def _message_is_vague(world_state: WorldState) -> bool:
    return bool(world_state.get("message_is_vague"))


def _intent_type_for_context(world_state: WorldState, belief_state: BeliefState) -> str:
    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")
    if health != "stable":
        return "relationship"
    if world_state.get("price_firm"):
        return "closing"
    if world_state.get("concession_made"):
        return "concession"
    if world_state.get("price_mentioned"):
        return "closing"
    if world_state.get("docs_claimed") or world_state.get("other_buyer_claimed"):
        return "credibility_check"
    return "info_extract"


def build_intent_contract(
    intent_type: str,
    world_state: WorldState,
    belief_state: BeliefState,
) -> tuple[list[str], list[str], str, list[str]]:
    if intent_type == "credibility_check" and world_state.get("other_buyer_claimed"):
        contract = INTENT_CONTRACTS["credibility_check"]
        return (
            list(contract["required"]),
            list(contract["optional"]),
            contract["goal"],
            list(contract["success_criteria"]),
        )

    contract = INTENT_CONTRACTS.get(intent_type, INTENT_CONTRACTS["info_extract"])
    return (
        list(contract["required"]),
        list(contract["optional"]),
        contract["goal"],
        list(contract["success_criteria"]),
    )


def build_steps(intent_type: str, missing: list[str]) -> list[IntentStep]:
    # P0: missing vacío debe producir un plan válido (sin slot fantasma)
    if not missing:
        return [dict(INTENT_CLOSE_STEP)]

    target = missing[0]
    return [
        {"kind": step, "target_slot": target, "success_if_filled": [target]}
        for step in INTENT_STEP_SEQUENCE
    ]


def _slot_entry(value: object, evidence: str, confidence: float, source: str = "world_state") -> dict:
    return {
        "value": value,
        "evidence": evidence,
        "confidence": confidence,
        "source": source,
    }


def _extract_slots(world_state: WorldState, user_message: str) -> dict:
    slots: dict = {}
    evidence = (user_message or "").strip()[:160]

    if world_state.get("price_mentioned"):
        price_value = world_state.get("price_value")
        slots["price"] = _slot_entry(
            price_value if price_value is not None else "mentioned",
            evidence,
            0.7,
        )

    if world_state.get("docs_claimed"):
        slots["docs"] = _slot_entry(world_state.get("docs_types", []), evidence, 0.6)

    if world_state.get("deadline_claimed"):
        slots["deadline_real"] = _slot_entry(world_state.get("deadline_text", ""), evidence, 0.6)

    if world_state.get("other_buyer_claimed"):
        other_buyer_text = world_state.get("other_buyer_text", "").strip()
        slots["other_buyer"] = _slot_entry("claimed", evidence, 0.5)
        slots["other_buyer_details"] = _slot_entry(
            {
                "claim_text": other_buyer_text,
                "offer_price": world_state.get("other_buyer_offer_price"),
                "timing": world_state.get("other_buyer_timing_text", "").strip(),
                "claim_confidence": 0.55,
            },
            evidence,
            0.65,
            source="world_state:other_buyer_claimed",
        )

    if world_state.get("concession_made"):
        slots["concession"] = _slot_entry(world_state.get("concession_text", ""), evidence, 0.6)

    if world_state.get("batna_claimed"):
        slots["seller_batna"] = _slot_entry(world_state.get("batna_text", ""), evidence, 0.6)

    if world_state.get("urgency_claimed"):
        slots["seller_urgency_reason"] = _slot_entry(
            world_state.get("urgency_text", ""), evidence, 0.6
        )

    if world_state.get("min_price_claimed"):
        slots["seller_min_acceptable"] = _slot_entry(
            world_state.get("min_price_text", ""), evidence, 0.6
        )

    if world_state.get("price_firm"):
        slots["price_firm"] = _slot_entry(world_state.get("price_firm_text", ""), evidence, 0.7)

    if world_state.get("evidence_offered"):
        slots["evidence_offered"] = _slot_entry(
            world_state.get("evidence_text", ""), evidence, 0.6
        )

    tone_signal = world_state.get("tone_signal")
    if tone_signal and tone_signal != "neutral":
        slots["tone_signal"] = _slot_entry(tone_signal, evidence, 0.5)
        if tone_signal == "friendly":
            slots["rapport_signal"] = _slot_entry("friendly", evidence, 0.4)

    return slots


def _slots_missing(intent_state: IntentState) -> list[str]:
    required = set(intent_state.get("slots", {}).get("slots_required", []))
    filled = set(intent_state.get("slots", {}).get("slots_filled", {}).keys())
    return sorted(required - filled)


def _world_has_multiple_open_factors(world_state: WorldState) -> bool:
    signals = [world_state.get(signal) for signal in OPEN_FACTOR_SIGNALS]
    return sum(1 for signal in signals if signal) >= 2


def _signal_quality(world_state: WorldState) -> float:
    evidence_items = world_state.get("evidence_items", []) or []
    if not evidence_items:
        return 0.0
    confidences = [float(item.get("confidence", 0.0)) for item in evidence_items]
    return sum(confidences) / max(len(confidences), 1)


def score_multi_turn_start(
    intent_type: str,
    slots_missing: list[str],
    world_state: WorldState,
    belief_state: BeliefState,
    user_message: str,
) -> MultiTurnScore:
    del user_message
    reasons: list[str] = []

    slots_missing_count = len(slots_missing)
    open_factors = sum(1 for signal in OPEN_FACTOR_SIGNALS if world_state.get(signal))
    signal_quality = _signal_quality(world_state)

    benefit = (
        INTENT_WEIGHT_SLOTS * slots_missing_count
        + INTENT_WEIGHT_OPEN_FACTORS * open_factors
        + INTENT_WEIGHT_UNCERTAINTY * (1.0 - signal_quality)
    )

    tension = 1.0 if belief_state.get("dynamics", {}).get("interaction_health") in {
        "tense",
        "stalled",
    } else 0.0
    urgency_pressure = 1.0 if world_state.get("deadline_days") in URGENCY_DEADLINE_DAYS else 0.0
    cost = (
        INTENT_COST_TENSION * tension
        + INTENT_COST_REPEAT * (1.0 if slots_missing_count <= 1 else 0.0)
        + INTENT_COST_URGENCY * urgency_pressure
    )

    utility = benefit - cost
    threshold = INTENT_START_UTILITY_THRESHOLD
    reasons.append(f"utility:{utility:.2f}")
    reasons.append(f"benefit:{benefit:.2f}")
    reasons.append(f"cost:{cost:.2f}")
    if intent_type in {"closing", "credibility_check"} and slots_missing:
        utility += 0.2
        reasons.append("priority_intent_boost")

    return MultiTurnScore(should_start=(utility >= threshold), score=int(round(utility * 10)), reasons=reasons)


def _commitment_level(intent_type: str, slots_missing: list[str], belief_state: BeliefState) -> str:
    if belief_state.get("dynamics", {}).get("interaction_health") != "stable":
        return "hard"
    if intent_type in {"closing", "concession", "credibility_check"}:
        return "hard"
    if any(slot in {"price", "deal_breakers"} for slot in slots_missing):
        return "hard"
    return "soft"


def _next_action_hint(step_kind: str, target_slot: str, slots_missing: list[str]) -> str:
    if step_kind == "probe_open":
        return f"Abrir con una pregunta amplia para desbloquear {target_slot}."
    if step_kind == "probe_narrow":
        return f"Pedir un dato concreto sobre {target_slot}."
    if step_kind == "request_evidence":
        return f"Solicitar evidencia concreta sobre {target_slot}."
    if step_kind == "trade_incentive":
        return f"Ofrecer un incentivo condicionado para obtener {target_slot}."
    if step_kind == "pressure_soft":
        return f"Aplicar presión suave para aclarar {target_slot}."
    if step_kind == "close_next":
        return "Cerrar el siguiente paso con confirmación breve."
    if slots_missing:
        return "Preguntar por los puntos faltantes más críticos."
    return "Mantener un avance gradual."


def _pivot_strategy_from_kind(step_kind: str) -> str:
    return PIVOT_KIND_MAPPING.get(step_kind, "open")


def _pivot_strategy_from_transition(prev_kind: str, new_kind: str) -> str:
    prev_label = _pivot_strategy_from_kind(prev_kind)
    new_label = _pivot_strategy_from_kind(new_kind)
    return f"{prev_label}_to_{new_label}"


def choose_pivot_kind(current_kind: StepKind) -> StepKind:
    order: list[StepKind] = list(INTENT_STEP_SEQUENCE)
    if current_kind in order:
        idx = order.index(current_kind)
        return order[min(idx + 1, len(order) - 1)]
    return order[0]


def maybe_retarget_steps(
    intent: IntentState,
    world_state: WorldState,
    user_message: str,
    meta: dict,
) -> None:
    del world_state, user_message
    step = _current_step(intent)
    if not step:
        return
    target = step.get("target_slot", "")
    if not target or target in {"unknown"}:
        return
    if target not in intent.get("slots", {}).get("slots_filled", {}):
        return
    missing = _slots_missing(intent)
    if not missing:
        return
    new_target = missing[0]
    intent["steps"] = build_steps(intent.get("intent_type", "info_extract"), missing)
    intent["step_idx"] = 0
    intent["step_attempts"] = 0
    meta["intent_transition"] = "retarget"
    meta["retarget_slot"] = new_target
    step = _current_step(intent)
    if step and step.get("target_slot") != new_target:
        meta.setdefault("reasons", []).append("retarget_step_mismatch")
        step["target_slot"] = new_target
    if step and step.get("success_if_filled") != [new_target]:
        meta.setdefault("reasons", []).append("retarget_success_mismatch")
        step["success_if_filled"] = [new_target]


def _should_advance_step(step: IntentStep, slots_delta: dict) -> bool:
    return any(slot in slots_delta for slot in step.get("success_if_filled", []))


def evaluate_success(
    intent: IntentState,
    world_state: WorldState,
    belief_state: BeliefState,
    meta: dict,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    criteria = intent.get("success_criteria", [])
    if not criteria:
        return False, []

    known = {
        *KNOWN_SUCCESS_CRITERIA,
    }
    for criterion in criteria:
        if criterion not in known:
            meta.setdefault("reasons", []).append(f"unknown_success_criterion:{criterion}")
            return False, []

    if "slots_required_complete" in criteria:
        if _slots_missing(intent) == []:
            reasons.append("slots_required_complete")
        else:
            return False, []

    if "firm_price_detected" in criteria:
        if world_state.get("price_firm"):
            reasons.append("firm_price_detected")
        else:
            return False, []

    if "evidence_offered" in criteria:
        if world_state.get("evidence_offered"):
            reasons.append("evidence_offered")
        else:
            return False, []

    return True, reasons


def _advance_step(intent: IntentState) -> None:
    if intent.get("steps") and intent.get("step_idx", 0) < len(intent["steps"]) - 1:
        intent["step_idx"] += 1


def _current_step(intent: IntentState) -> IntentStep | None:
    if not intent.get("steps"):
        return None
    step_idx = min(intent.get("step_idx", 0), len(intent["steps"]) - 1)
    return intent["steps"][step_idx]


def _normalize_slots_filled_sources(intent: IntentState) -> None:
    """
    P0 migration: legacy states may have IntentSlot without 'source'.
    This normalizes them in-place to keep runtime/schema consistent.
    """
    slots = intent.get("slots") or {}
    slots_filled = slots.get("slots_filled") or {}
    for _k, payload in list(slots_filled.items()):
        if isinstance(payload, dict) and "source" not in payload:
            payload["source"] = "legacy"


def _ensure_steps_hydrated(
    intent: IntentState,
    world_state: WorldState,
    belief_state: BeliefState,
    meta: dict,
) -> IntentState:
    del world_state, belief_state
    if intent.get("status") != "active":
        return intent
    steps = intent.get("steps")
    step = _current_step(intent)
    if (
        not isinstance(steps, list)
        or not steps
        or not step
        or not isinstance(step, dict)
        or step.get("target_slot") in {"", "unknown"}
    ):
        missing = _slots_missing(intent)
        if not missing:
            intent["steps"] = [dict(INTENT_CLOSE_STEP)]
        else:
            intent["steps"] = build_steps(intent.get("intent_type", "info_extract"), missing)
        intent["step_idx"] = 0
        intent["step_attempts"] = 0
        meta.setdefault("reasons", []).append("steps_hydrated")
    return intent


def _should_replan(
    intent: IntentState, world_state: WorldState, precedence: dict | None
) -> str | None:
    evidence_items = world_state.get("evidence_items", [])
    threshold = INTENT_FIRMNESS_REPLAN_THRESHOLD
    strong_firmness = any(
        item.get("type") == "FIRMNESS"
        and (item.get("field") in {"price_firm", "", None})
        and item.get("polarity", "affirm") == "affirm"
        and float(item.get("confidence", 0.0)) >= threshold
        for item in evidence_items
    )
    has_price_value = world_state.get("price_mentioned") and world_state.get("price_value") is not None
    if strong_firmness and has_price_value and intent.get("intent_type") != "closing":
        if (precedence or {}).get("mode") == "recovery_guard":
            return "relationship"
        return "closing"
    return None


def _evidence_delta_for_slot(prev_world: WorldState, world: WorldState, slot: str) -> bool:
    slot_to_fields = {
        "price": {"price_value", "price_mentioned"},
        "docs": {"docs_claimed", "docs_types"},
        "seller_batna": {"batna_claimed"},
        "seller_urgency_reason": {"urgency_reason", "urgency_claimed"},
    }
    fields = slot_to_fields.get(slot, set())
    if not fields:
        return False

    def _key(item: dict) -> tuple:
        return (
            item.get("type"),
            item.get("field"),
            item.get("polarity", "affirm"),
            str(item.get("value")),
            item.get("source"),
            (item.get("text") or "").strip()[:60].lower(),
        )

    prev = {
        _key(item)
        for item in (prev_world.get("evidence_items", []) or [])
        if isinstance(item, dict) and item.get("field") in fields
    }
    for item in (world.get("evidence_items", []) or []):
        if not isinstance(item, dict):
            continue
        if item.get("field") not in fields:
            continue
        if _key(item) not in prev:
            return True
    return False


def update_intent_state(
    prev_intent: IntentState | None,
    prev_world_state: WorldState | None,
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    user_message: str,
    turn_count: int,
    precedence: dict | None,
) -> Tuple[IntentState, dict, dict]:
    intent = deepcopy(prev_intent or default_intent_state())
    prev_world = prev_world_state or default_world_state()
    _normalize_slots_filled_sources(intent)
    meta = {
        "intent_prev": deepcopy(intent),
        "intent_new": {},
        "intent_decision": "",
        "intent_transition": "none",
        "retarget_slot": "",
        "replan_to": "",
        "pivot_reason": "",
        "pivot_strategy": "",
        "success_reasons": [],
        "reasons": [],
        "slots_filled_delta": {},
        "commitment_level": "soft",
    }

    prec = precedence or {}

    if intent.get("status") != "active":
        intent_type = _intent_type_for_context(world_state, belief_state)
        required, optional, goal, success_criteria = build_intent_contract(
            intent_type, world_state, belief_state
        )
        intent["intent_type"] = intent_type
        intent["intent_goal"] = goal
        intent["slots"] = {
            "slots_required": required,
            "slots_optional": optional,
            "slots_filled": _extract_slots(world_state, user_message),
        }
        slots_missing = _slots_missing(intent)
        score = score_multi_turn_start(
            intent_type, slots_missing, world_state, belief_state, user_message
        )
        meta["reasons"].extend(score.reasons)
        meta["reasons"].append(f"multi_turn_score:{score.score}")
        meta["commitment_level"] = _commitment_level(intent_type, slots_missing, belief_state)

        if score.should_start:
            intent["status"] = "active"
            intent["steps"] = build_steps(intent_type, slots_missing)
            intent["step_idx"] = 0
            intent["step_attempts"] = 0
            intent["max_attempts_per_step"] = INTENT_MAX_ATTEMPTS_PER_STEP
            intent["success_criteria"] = success_criteria or ["slots_required_complete"]
            intent["confidence"] = 0.4
            intent["created_turn"] = turn_count
            intent["last_turn"] = turn_count
            intent["continue_until"] = "slots_required_complete"
            intent["no_progress_turns"] = 0
            intent["slot_fill_count"] = len(intent["slots"]["slots_filled"])
            intent["slot_fill_count_recent"] = len(intent["slots"]["slots_filled"])
            step = _current_step(intent)
            intent["next_action_hint"] = _next_action_hint(
                step["kind"] if step else "",
                step["target_slot"] if step else "",
                slots_missing,
            )
            intent["last_observation"] = "Inicio de intención multi-turno."
            meta["intent_decision"] = "commit"
        else:
            intent = default_intent_state()
            intent["last_turn"] = turn_count
            meta["intent_decision"] = "inactive"

        meta["intent_new"] = deepcopy(intent)
        intent_hint = _build_intent_hint(intent, slots_missing, meta["commitment_level"])
        return intent, meta, intent_hint

    if prec.get("mode") == "recovery_guard":
        if intent.get("status") == "active" and intent.get("intent_type") not in {"relationship"}:
            intent["status"] = "paused"
            meta["intent_transition"] = "pause"
            meta["reasons"] = (meta.get("reasons", []) + ["precedence:recovery_guard"])[:8]
            meta["intent_new"] = deepcopy(intent)
            intent_hint = _build_intent_hint(intent, _slots_missing(intent), "soft")
            return intent, meta, intent_hint

    intent = _ensure_steps_hydrated(intent, world_state, belief_state, meta)

    slots_filled = dict(intent.get("slots", {}).get("slots_filled", {}))
    extracted = _extract_slots(world_state, user_message)
    for key, payload in extracted.items():
        if key not in slots_filled:
            slots_filled[key] = payload
            meta["slots_filled_delta"][key] = payload
    intent["slots"]["slots_filled"] = slots_filled

    slots_missing = _slots_missing(intent)
    commitment = _commitment_level(
        intent.get("intent_type", "info_extract"), slots_missing, belief_state
    )
    meta["commitment_level"] = commitment

    replan_to = _should_replan(intent, world_state, precedence)
    if replan_to:
        intent_type = replan_to
        required, optional, goal, success_criteria = build_intent_contract(
            intent_type, world_state, belief_state
        )
        intent = default_intent_state()
        intent["intent_type"] = intent_type
        intent["intent_goal"] = goal
        intent["slots"] = {
            "slots_required": required,
            "slots_optional": optional,
            "slots_filled": _extract_slots(world_state, user_message),
        }
        slots_missing = _slots_missing(intent)
        intent["status"] = "active"
        intent["steps"] = build_steps(intent_type, slots_missing)
        intent["step_idx"] = 0
        intent["step_attempts"] = 0
        intent["max_attempts_per_step"] = INTENT_MAX_ATTEMPTS_PER_STEP
        intent["success_criteria"] = success_criteria or ["slots_required_complete"]
        intent["confidence"] = 0.4
        intent["created_turn"] = turn_count
        intent["last_turn"] = turn_count
        intent["continue_until"] = "slots_required_complete"
        step = _current_step(intent)
        intent["next_action_hint"] = _next_action_hint(
            step["kind"] if step else "",
            step["target_slot"] if step else "",
            slots_missing,
        )
        intent["last_observation"] = "Replan hacia cierre por señal fuerte."
        meta["intent_decision"] = "replan"
        meta["intent_transition"] = "replan"
        meta["replan_to"] = intent_type
        meta["intent_new"] = deepcopy(intent)
        intent_hint = _build_intent_hint(intent, slots_missing, commitment)
        return intent, meta, intent_hint

    maybe_retarget_steps(intent, world_state, user_message, meta)
    retargeted = meta.get("intent_transition", "") == "retarget"
    slots_missing = _slots_missing(intent)

    slots_filled = intent.get("slots", {}).get("slots_filled", {})
    prev_slots = meta.get("intent_prev", {}).get("slots", {})
    prev_required = set(prev_slots.get("slots_required", []))
    prev_filled = set(prev_slots.get("slots_filled", {}).keys())
    prev_missing_count = len(prev_required - prev_filled)
    current_missing_count = len(slots_missing)
    current_step = _current_step(intent)
    slots_delta = current_missing_count < prev_missing_count
    target_slot = current_step["target_slot"] if current_step else ""
    evidence_delta = bool(target_slot) and _evidence_delta_for_slot(
        prev_world, world_state, target_slot
    )
    progress_made = True if not prev_required else (slots_delta or evidence_delta)
    if progress_made:
        intent["no_progress_turns"] = 0
    else:
        intent["no_progress_turns"] = intent.get("no_progress_turns", 0) + 1
    intent["slot_fill_count"] = len(slots_filled)
    intent["slot_fill_count_recent"] = len(meta.get("slots_filled_delta", {}))
    base_confidence = float(intent.get("confidence", 0.4) or 0.4)
    if base_confidence <= 0.0:
        base_confidence = 0.4
    if not progress_made:
        intent["confidence"] = max(
            0.0,
            base_confidence - INTENT_CONFIDENCE_DECAY,
        )
    else:
        intent["confidence"] = base_confidence

    succeeded, success_reasons = evaluate_success(intent, world_state, belief_state, meta)
    if succeeded:
        intent["status"] = "succeeded"
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Criterios mínimos completados."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "succeed"
        meta["intent_transition"] = "succeed"
        meta["success_reasons"] = success_reasons
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, [], commitment)

    if belief_state.get("dynamics", {}).get("interaction_health") == "tense":
        intent["status"] = "abandoned"
        intent["abandon_reasons"] = list(intent.get("abandon_reasons", [])) + [
            "interaction_tense",
        ]
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Señal de tensión alta."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "abandon"
        meta["intent_transition"] = "abandon"
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, slots_missing, commitment)

    if "stuck_in_policy" in progress_state.get("loop_flags", []):
        intent["status"] = "abandoned"
        intent["abandon_reasons"] = list(intent.get("abandon_reasons", [])) + [
            "loop_detected",
        ]
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Estancamiento detectado."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "abandon"
        meta["intent_transition"] = "abandon"
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, slots_missing, commitment)

    max_total_turns = INTENT_MAX_TURNS
    if turn_count - intent.get("created_turn", turn_count) >= max_total_turns:
        intent["status"] = "abandoned"
        intent["abandon_reasons"] = list(intent.get("abandon_reasons", [])) + [
            "max_turns_exceeded",
        ]
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Se agotó el tiempo de intento."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "abandon"
        meta["intent_transition"] = "abandon"
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, slots_missing, commitment)

    step = _current_step(intent)

    if retargeted:
        intent["step_attempts"] = 0
        meta["intent_decision"] = "retarget"
    elif step and _should_advance_step(step, meta["slots_filled_delta"]):
        _advance_step(intent)
        intent["step_attempts"] = 0
        meta["intent_decision"] = "advance"
        meta["intent_transition"] = "advance"
    else:
        if "steps_hydrated" in meta.get("reasons", []):
            intent["step_attempts"] = 0
            meta["intent_decision"] = "continue"
        else:
            intent["step_attempts"] = intent.get("step_attempts", 0) + 1
            pivot_reason = ""
            if _message_is_vague(world_state):
                meta["reasons"].append("vague_response")
                pivot_reason = "vague"
            elif step and step.get("kind") == "request_evidence" and not world_state.get(
                "evidence_offered"
            ):
                pivot_reason = "no_evidence"

            if intent["step_attempts"] >= intent.get("max_attempts_per_step", 2):
                if pivot_reason:
                    prev_kind = step.get("kind", "probe_open") if step else "probe_open"
                    new_kind = choose_pivot_kind(prev_kind)
                    if step:
                        step["kind"] = new_kind
                    intent["step_attempts"] = 0
                    meta["intent_decision"] = "pivot"
                    meta["intent_transition"] = "pivot"
                    meta["pivot_reason"] = pivot_reason
                    meta["pivot_strategy"] = _pivot_strategy_from_transition(prev_kind, new_kind)
                else:
                    _advance_step(intent)
                    intent["step_attempts"] = 0
                    meta["intent_decision"] = "advance"
                    meta["intent_transition"] = "advance"
            else:
                meta["intent_decision"] = "continue"

    no_progress_limit = INTENT_NO_PROGRESS_ABORT_TURNS
    steps = intent.get("steps", [])
    is_last_step = bool(steps) and intent.get("step_idx", 0) >= len(steps) - 1
    if (
        intent.get("no_progress_turns", 0) >= no_progress_limit
        and is_last_step
        and meta.get("intent_decision") not in {"pivot", "retarget"}
    ) or intent.get("confidence", 0.0) < 0.15:
        intent["status"] = "abandoned"
        intent["abandon_reasons"] = list(intent.get("abandon_reasons", [])) + [
            "no_progress",
        ]
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Se estancó la intención."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "abandon"
        meta["intent_transition"] = "abandon"
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, slots_missing, commitment)

    step = _current_step(intent)
    intent["next_action_hint"] = _next_action_hint(
        step["kind"] if step else "",
        step["target_slot"] if step else "",
        slots_missing,
    )
    intent["last_turn"] = turn_count
    intent["last_observation"] = "Continúa la intención activa."

    meta["intent_new"] = deepcopy(intent)
    intent_hint = _build_intent_hint(intent, slots_missing, commitment)
    return intent, meta, intent_hint


def _build_intent_hint(intent: IntentState, slots_missing: list[str], commitment: str) -> IntentHint:
    step = _current_step(intent)
    step_kind = step["kind"] if step else ""
    target_slot = step["target_slot"] if step else ""
    slots_filled = intent.get("slots", {}).get("slots_filled", {})
    filled_summary = ", ".join(sorted(slots_filled.keys())) if slots_filled else ""
    return {
        "intent_active": intent.get("status") == "active",
        "intent_goal": intent.get("intent_goal", ""),
        "intent_type": intent.get("intent_type", ""),
        "step_kind": step_kind,
        "target_slot": target_slot,
        "next_action_hint": intent.get("next_action_hint", ""),
        "slots_missing": slots_missing,
        "slots_filled_summary": filled_summary,
        "commitment_level": commitment,
    }
