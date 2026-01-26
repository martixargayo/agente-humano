from __future__ import annotations

from copy import deepcopy
from typing import Tuple

from .schemas import BeliefState, IntentState, ProgressState, WorldState, default_intent_state


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


def _is_vague(message: str) -> bool:
    lowered = (message or "").lower()
    return any(marker in lowered for marker in _VAGUE_MARKERS)


def _intent_type_for_context(world_state: WorldState, belief_state: BeliefState) -> str:
    health = belief_state.get("dynamics", {}).get("interaction_health", "stable")
    if health != "stable":
        return "relationship"
    if world_state.get("concession_made"):
        return "concession"
    if world_state.get("price_mentioned"):
        return "closing"
    if world_state.get("docs_claimed") or world_state.get("other_buyer_claimed"):
        return "credibility_check"
    return "info_extract"


def _intent_slots_for_type(intent_type: str) -> tuple[list[str], list[str]]:
    if intent_type == "relationship":
        return ["tone_signal"], ["rapport_signal"]
    if intent_type == "concession":
        return ["concession"], ["price"]
    if intent_type == "closing":
        return ["price", "concession"], ["docs"]
    if intent_type == "credibility_check":
        return ["docs", "other_buyer"], ["deadline_real"]
    return ["price", "docs"], ["deadline_real", "other_buyer", "concession"]


def _intent_steps(intent_type: str) -> list[str]:
    if intent_type == "relationship":
        return ["deescalate", "rebuild", "advance"]
    if intent_type == "concession":
        return ["probe", "tradeoff", "close"]
    if intent_type == "closing":
        return ["summarize", "confirm_terms", "close"]
    if intent_type == "credibility_check":
        return ["ask_evidence", "probe_details", "validate"]
    return ["ask_open", "narrow", "validate", "leverage"]


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
        slots["other_buyer"] = _slot_entry("claimed", evidence, 0.5)

    if world_state.get("concession_made"):
        slots["concession"] = _slot_entry(world_state.get("concession_text", ""), evidence, 0.6)

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


def _should_require_multi_turn(
    intent_type: str,
    slots_missing: list[str],
    world_state: WorldState,
    belief_state: BeliefState,
    user_message: str,
) -> bool:
    if slots_missing:
        return True
    if intent_type in {"info_extract", "relationship", "concession", "closing", "credibility_check"}:
        if _is_vague(user_message):
            return True
    if belief_state.get("dynamics", {}).get("interaction_health") != "stable":
        return True

    multiparam_signals = 0
    if world_state.get("price_mentioned"):
        multiparam_signals += 1
    if world_state.get("docs_claimed"):
        multiparam_signals += 1
    if world_state.get("deadline_claimed"):
        multiparam_signals += 1
    if world_state.get("other_buyer_claimed"):
        multiparam_signals += 1
    return multiparam_signals >= 2


def _commitment_level(intent_type: str, slots_missing: list[str], belief_state: BeliefState) -> str:
    if belief_state.get("dynamics", {}).get("interaction_health") != "stable":
        return "hard"
    if intent_type in {"closing", "concession", "credibility_check"}:
        return "hard"
    if any(slot in {"price", "deal_breakers"} for slot in slots_missing):
        return "hard"
    return "soft"


def _next_action_hint(step_name: str, slots_missing: list[str]) -> str:
    if step_name == "ask_open":
        return "Abrir con una pregunta amplia para desbloquear información clave."
    if step_name == "narrow":
        return "Pedir un dato concreto sobre los puntos pendientes."
    if step_name == "validate":
        return "Confirmar o validar con evidencia lo que falta."
    if step_name == "leverage":
        return "Usar la información obtenida para avanzar condiciones."
    if step_name == "deescalate":
        return "Bajar tensión y mostrar disposición a escuchar."
    if step_name == "rebuild":
        return "Recomponer confianza antes de volver a negociar."
    if step_name == "advance":
        return "Retomar la negociación con un paso suave."
    if step_name == "probe":
        return "Explorar margen de concesión sin comprometerse."
    if step_name == "tradeoff":
        return "Proponer intercambio concreto."
    if step_name == "close":
        return "Cerrar con condiciones claras y breves."
    if step_name == "summarize":
        return "Resumir términos clave antes de cerrar."
    if step_name == "confirm_terms":
        return "Confirmar los términos pendientes."
    if step_name == "ask_evidence":
        return "Solicitar evidencia concreta."
    if step_name == "probe_details":
        return "Profundizar en detalles verificables."
    if slots_missing:
        return "Preguntar por los puntos faltantes más críticos."
    return "Mantener un avance gradual."


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
        "intent_decision": "",
        "reasons": [],
        "slots_filled_delta": {},
        "commitment_level": "soft",
    }

    if intent.get("status") != "active":
        intent_type = _intent_type_for_context(world_state, belief_state)
        required, optional = _intent_slots_for_type(intent_type)
        intent["intent_type"] = intent_type
        intent["slots"] = {
            "slots_required": required,
            "slots_optional": optional,
            "slots_filled": {},
        }
        slots_missing = _slots_missing(intent)
        if _should_require_multi_turn(
            intent_type, slots_missing, world_state, belief_state, user_message
        ):
            intent["status"] = "active"
            intent["intent_goal"] = "Avanzar la negociación con foco en información crítica."
            intent["steps"] = _intent_steps(intent_type)
            intent["step_idx"] = 0
            intent["step_attempts"] = 0
            intent["max_attempts_per_step"] = 2
            intent["success_criteria"] = ["slots_required_complete"]
            intent["confidence"] = 0.4
            intent["created_turn"] = turn_count
            intent["last_turn"] = turn_count
            intent["continue_until"] = "slots_required_complete"
            step_name = intent["steps"][0] if intent["steps"] else ""
            intent["next_action_hint"] = _next_action_hint(step_name, slots_missing)
            intent["last_observation"] = "Inicio de intención multi-turno."
            meta["intent_decision"] = "commit"
        else:
            intent = default_intent_state()
            intent["last_turn"] = turn_count
            meta["intent_decision"] = "inactive"
        meta["commitment_level"] = _commitment_level(
            intent.get("intent_type", "info_extract"), slots_missing, belief_state
        )
        meta["intent_new"] = deepcopy(intent)
        intent_hint = _build_intent_hint(intent, slots_missing, meta["commitment_level"])
        return intent, meta, intent_hint

    slots_filled = dict(intent.get("slots", {}).get("slots_filled", {}))
    extracted = _extract_slots(world_state, user_message)
    for key, payload in extracted.items():
        if key not in slots_filled:
            slots_filled[key] = payload
            meta["slots_filled_delta"][key] = payload
    intent["slots"]["slots_filled"] = slots_filled

    slots_missing = _slots_missing(intent)
    commitment = _commitment_level(intent.get("intent_type", "info_extract"), slots_missing, belief_state)
    meta["commitment_level"] = commitment

    if not slots_missing:
        intent["status"] = "succeeded"
        intent["next_action_hint"] = ""
        intent["last_observation"] = "Criterios mínimos completados."
        intent["last_turn"] = turn_count
        meta["intent_decision"] = "succeed"
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
        meta["intent_new"] = deepcopy(intent)
        return intent, meta, _build_intent_hint(intent, slots_missing, commitment)

    step_name = ""
    if intent.get("steps"):
        step_idx = min(intent.get("step_idx", 0), len(intent["steps"]) - 1)
        step_name = intent["steps"][step_idx]

    if meta["slots_filled_delta"]:
        if intent.get("steps") and intent.get("step_idx", 0) < len(intent["steps"]) - 1:
            intent["step_idx"] += 1
        intent["step_attempts"] = 0
        meta["intent_decision"] = "advance"
    else:
        intent["step_attempts"] = intent.get("step_attempts", 0) + 1
        if intent["step_attempts"] >= intent.get("max_attempts_per_step", 2):
            if intent.get("steps") and intent.get("step_idx", 0) < len(intent["steps"]) - 1:
                intent["step_idx"] += 1
            intent["step_attempts"] = 0
            meta["intent_decision"] = "advance"
        else:
            meta["intent_decision"] = "continue"

    if intent.get("steps"):
        step_idx = min(intent.get("step_idx", 0), len(intent["steps"]) - 1)
        step_name = intent["steps"][step_idx]
    intent["next_action_hint"] = _next_action_hint(step_name, slots_missing)
    intent["last_turn"] = turn_count
    intent["last_observation"] = "Continúa la intención activa."

    meta["intent_new"] = deepcopy(intent)
    intent_hint = _build_intent_hint(intent, slots_missing, commitment)
    return intent, meta, intent_hint


def _build_intent_hint(intent: IntentState, slots_missing: list[str], commitment: str) -> dict:
    step_name = ""
    if intent.get("steps"):
        step_idx = min(intent.get("step_idx", 0), len(intent["steps"]) - 1)
        step_name = intent["steps"][step_idx]
    slots_filled = intent.get("slots", {}).get("slots_filled", {})
    filled_summary = ", ".join(sorted(slots_filled.keys())) if slots_filled else ""
    return {
        "intent_active": intent.get("status") == "active",
        "intent_goal": intent.get("intent_goal", ""),
        "intent_type": intent.get("intent_type", ""),
        "step_name": step_name,
        "next_action_hint": intent.get("next_action_hint", ""),
        "slots_missing": slots_missing,
        "slots_filled_summary": filled_summary,
        "commitment_level": commitment,
    }
