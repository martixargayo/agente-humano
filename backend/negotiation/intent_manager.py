from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import List, Tuple

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


_VAGUE_MARKERS = [
    "depende",
    "ya veremos",
    "más adelante",
    "no sé",
    "no lo sé",
    "lo normal",
    "quizá",
    "tal vez",
]


@dataclass(frozen=True)
class MultiTurnScore:
    should_start: bool
    score: int
    reasons: List[str]


def _is_vague(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _VAGUE_MARKERS)


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
        goal = (
            "Verificar si el 'otro comprador' es real y extraer detalles verificables sin revelar "
            "mi límite."
        )
        required = ["other_buyer_details", "evidence_offered"]
        optional = ["deadline_real", "price_firm"]
        return required, optional, goal, ["slots_required_complete", "evidence_offered"]

    if intent_type == "closing":
        goal = "Confirmar si el precio es firme y definir condiciones mínimas antes de cerrar."
        required = ["price", "price_firm"]
        optional = ["concession", "docs"]
        return required, optional, goal, ["slots_required_complete", "firm_price_detected"]

    if intent_type == "concession":
        goal = "Aclarar concesiones reales y margen sin comprometerse."
        required = ["concession"]
        optional = ["price", "seller_min_acceptable"]
        return required, optional, goal, ["slots_required_complete"]

    if intent_type == "relationship":
        goal = "Bajar tensión y restablecer señales de cooperación."
        required = ["tone_signal"]
        optional = ["rapport_signal"]
        return required, optional, goal, ["slots_required_complete"]

    goal = "Descubrir la urgencia real y la alternativa del vendedor (BATNA) para calibrar margen."
    required = ["seller_batna", "seller_urgency_reason"]
    optional = ["seller_min_acceptable", "price_firm"]
    return required, optional, goal, ["slots_required_complete"]


def build_steps(intent_type: str, missing: list[str]) -> list[IntentStep]:
    target = missing[0] if missing else "confirm_close"
    return [
        {"kind": "probe_open", "target_slot": target, "success_if_filled": [target]},
        {"kind": "probe_narrow", "target_slot": target, "success_if_filled": [target]},
        {"kind": "request_evidence", "target_slot": target, "success_if_filled": [target]},
        {"kind": "trade_incentive", "target_slot": target, "success_if_filled": [target]},
        {"kind": "pressure_soft", "target_slot": target, "success_if_filled": [target]},
    ]


def _slot_entry(value: object, evidence: str, confidence: float) -> dict:
    return {
        "value": value,
        "evidence": evidence,
        "confidence": confidence,
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
    signals = [
        world_state.get("price_mentioned"),
        world_state.get("docs_claimed"),
        world_state.get("deadline_claimed"),
        world_state.get("other_buyer_claimed"),
        world_state.get("batna_claimed"),
        world_state.get("urgency_claimed"),
        world_state.get("min_price_claimed"),
        world_state.get("price_firm"),
        world_state.get("evidence_offered"),
    ]
    return sum(1 for signal in signals if signal) >= 2


def score_multi_turn_start(
    intent_type: str,
    slots_missing: list[str],
    world_state: WorldState,
    belief_state: BeliefState,
    user_message: str,
) -> MultiTurnScore:
    score = 0
    reasons: list[str] = []

    if len(slots_missing) >= 2:
        score += 2
        reasons.append("slots_missing>=2")
    elif len(slots_missing) == 1:
        score += 1
        reasons.append("slots_missing=1")

    if _is_vague(user_message):
        score += 2
        reasons.append("vague_response")

    if _world_has_multiple_open_factors(world_state):
        score += 1
        reasons.append("multiple_open_factors")

    if belief_state.get("dynamics", {}).get("interaction_health") in {"tense", "stalled"}:
        score += 2
        reasons.append("relationship_tense_or_stalled")

    if intent_type in {"closing", "credibility_check"} and slots_missing:
        score += 1
        reasons.append("priority_intent_with_missing")

    return MultiTurnScore(should_start=(score >= 3), score=score, reasons=reasons)


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
    mapping = {
        "probe_open": "open",
        "probe_narrow": "narrow",
        "request_evidence": "evidence",
        "trade_incentive": "incentive",
        "pressure_soft": "soft_pressure",
        "close_next": "narrow",
    }
    return mapping.get(step_kind, "open")


def _pivot_strategy_from_transition(prev_kind: str, new_kind: str) -> str:
    prev_label = _pivot_strategy_from_kind(prev_kind)
    new_label = _pivot_strategy_from_kind(new_kind)
    return f"{prev_label}_to_{new_label}"


def choose_pivot_kind(current_kind: StepKind) -> StepKind:
    order: list[StepKind] = [
        "probe_open",
        "probe_narrow",
        "request_evidence",
        "trade_incentive",
        "pressure_soft",
    ]
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
        "slots_required_complete",
        "firm_price_detected",
        "evidence_offered",
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
        intent["steps"] = build_steps(intent.get("intent_type", "info_extract"), missing)
        intent["step_idx"] = 0
        intent["step_attempts"] = 0
        meta.setdefault("reasons", []).append("steps_hydrated")
    return intent


def _should_replan(intent: IntentState, world_state: WorldState) -> str | None:
    if world_state.get("price_firm") and intent.get("intent_type") != "closing":
        return "closing"
    return None


def update_intent_state(
    prev_intent: IntentState | None,
    world_state: WorldState,
    belief_state: BeliefState,
    progress_state: ProgressState,
    user_message: str,
    turn_count: int,
) -> Tuple[IntentState, dict, dict]:
    intent = deepcopy(prev_intent or default_intent_state())
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
            intent["max_attempts_per_step"] = 2
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
            intent["last_observation"] = "Inicio de intención multi-turno."
            meta["intent_decision"] = "commit"
        else:
            intent = default_intent_state()
            intent["last_turn"] = turn_count
            meta["intent_decision"] = "inactive"

        meta["intent_new"] = deepcopy(intent)
        intent_hint = _build_intent_hint(intent, slots_missing, meta["commitment_level"])
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

    replan_to = _should_replan(intent, world_state)
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
        intent["max_attempts_per_step"] = 2
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

    max_total_turns = 6
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
        intent["step_attempts"] = intent.get("step_attempts", 0) + 1
        pivot_reason = ""
        if _is_vague(user_message):
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
