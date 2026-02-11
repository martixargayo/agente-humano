# backend/negotiation/policies.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set

from .schemas import NegotiationPhase, RequiredInput


@dataclass(frozen=True)
class Policy:
    policy_id: str
    description: str
    primary_when: str
    hard_constraints: str
    hard_constraints_rules: List[str]
    rag_query_template: str
    phase_hints: List[NegotiationPhase]
    required_inputs: List[RequiredInput]
    target_slots: List[str]
    expected_effects: List[str]
    failure_modes: List[str]
    capabilities: Set[str] | None = None
    guards: Set[str] | None = None
    tags: Set[str] | None = None


POLICIES: List[Policy] = [
    Policy(
        policy_id="safe_neutral",
        description="Respuesta segura y neutral para mantener la conversación.",
        primary_when="No hay señales claras o se omite el planner.",
        hard_constraints="No escalar ni presionar; mantener tono cordial.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template="Frases neutrales y seguras para mantener la conversación.",
        phase_hints=["opening", "recovery", "discovery"],
        required_inputs=[],
        target_slots=["rapport_signal"],
        expected_effects=["keeps_dialogue_open"],
        failure_modes=["seller_repeats_same_answer"],
        capabilities={"probe_open"},
        guards={"safe_when_tense", "avoid_mentioning_own_numbers"},
        tags={"safe_neutral"},
    ),
    Policy(
        policy_id="rapport_build",
        description="Construir clima cordial y reducir fricciones.",
        primary_when="Inicio de la interacción o clima frío.",
        hard_constraints="No presionar el precio ni confrontar directamente.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Tácticas para generar rapport sin perder objetivo en una negociación presencial."
        ),
        phase_hints=["opening", "recovery"],
        required_inputs=[{"key": "tone_signal", "op": "exists"}],
        target_slots=["rapport_signal"],
        expected_effects=["reduces_tension", "opens_dialogue"],
        failure_modes=["seller_repeats_same_answer", "high_tension"],
        capabilities={"probe_open"},
        guards={"safe_when_tense", "avoid_mentioning_own_numbers"},
        tags={"deescalation", "safe_when_tense"},
    ),
    Policy(
        policy_id="info_extract_critical",
        description="Extraer información crítica del coche y del vendedor.",
        primary_when="Faltan datos clave o el vendedor es ambiguo.",
        hard_constraints="No comprometerse con precio aún.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Preguntas y técnicas para descubrir información crítica sin sonar interrogatorio."
        ),
        phase_hints=["discovery", "opening"],
        required_inputs=[],
        target_slots=["docs", "seller_batna", "seller_urgency_reason"],
        expected_effects=["seller_provides_docs", "seller_explains_urgency"],
        failure_modes=["seller_dodges_details", "message_is_vague"],
        capabilities={"probe_open", "probe_narrow"},
        guards={"avoid_mentioning_own_numbers", "safe_when_tense"},
        tags={"bargaining"},
    ),
    Policy(
        policy_id="test_credibility",
        description="Poner a prueba consistencia o veracidad del vendedor.",
        primary_when="Se detectan inconsistencias, urgencias o excusas.",
        hard_constraints="Evitar acusaciones directas; mantener tono calmado.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Cómo contrastar credibilidad con preguntas indirectas y señales suaves."
        ),
        phase_hints=["discovery", "opening"],
        required_inputs=[{"key": "other_buyer_claimed", "op": "true"}],
        target_slots=["other_buyer_details", "evidence_offered"],
        expected_effects=["seller_offers_evidence", "clarifies_other_buyer"],
        failure_modes=["seller_refuses_details", "high_tension"],
        capabilities={"request_evidence", "probe_narrow"},
        guards={"safe_when_tense", "avoid_mentioning_own_numbers"},
        tags={"credibility_check"},
    ),
    Policy(
        policy_id="delay_price_discussion",
        description="Posponer el precio para mantener control del ritmo.",
        primary_when="El vendedor quiere cerrar precio muy pronto.",
        hard_constraints="No discutir cifras ni anclas numéricas propias.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Tácticas para aplazar precio y reconducir a información o valor."
        ),
        phase_hints=["discovery", "opening"],
        required_inputs=[{"key": "price_mentioned", "op": "exists"}],
        target_slots=["docs", "seller_batna"],
        expected_effects=["shifts_to_info", "reduces_price_focus"],
        failure_modes=["seller_insists_on_price"],
        capabilities={"probe_open"},
        guards={"avoid_mentioning_own_numbers", "requires_price_not_mentioned"},
        tags={"bargaining"},
    ),
    Policy(
        policy_id="challenge_anchor_indirect",
        description="Cuestionar el ancla de precio sin confrontar.",
        primary_when="Hay ancla alta o presión por precio.",
        hard_constraints="No revelar límite 10k ni alternativa explícita.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Formas indirectas de desafiar un precio alto y abrir espacio."
        ),
        phase_hints=["bargaining", "closing"],
        required_inputs=[{"key": "price_mentioned", "op": "true"}],
        target_slots=["price", "concession"],
        expected_effects=["seller_considers_drop", "signals_flexibility"],
        failure_modes=["seller_hard_firmness", "high_tension"],
        capabilities={"pressure_soft"},
        guards={"avoid_mentioning_own_numbers"},
        tags={"bargaining", "aggressive"},
    ),
    Policy(
        policy_id="tradeoff_offer",
        description="Proponer intercambio: precio vs. condiciones o extras.",
        primary_when="Hay margen para concesiones recíprocas.",
        hard_constraints="No ceder gratis; siempre pedir algo a cambio.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Cómo formular trade-offs claros que mantengan control del valor."
        ),
        phase_hints=["bargaining", "closing"],
        required_inputs=[{"key": "price_mentioned", "op": "true"}],
        target_slots=["concession", "docs"],
        expected_effects=["seller_offers_extra", "seller_moves_on_price"],
        failure_modes=["seller_rejects_tradeoff"],
        capabilities={"trade_incentive"},
        guards={"avoid_mentioning_own_numbers"},
        tags={"bargaining"},
    ),
    Policy(
        policy_id="hold_position",
        description="Mantener postura firme sin escalar conflicto.",
        primary_when="Necesitas sostener un límite o no moverte más.",
        hard_constraints="No sonar ultimátum ni romper la relación.",
        hard_constraints_rules=["avoid_reveal_own_numbers", "respect_batna"],
        rag_query_template=(
            "Frases breves para mantener posición y seguir negociando."
        ),
        phase_hints=["bargaining", "closing"],
        required_inputs=[{"key": "price_mentioned", "op": "true"}],
        target_slots=["price", "price_firm"],
        expected_effects=["seller_acknowledges_limit", "stabilizes_terms"],
        failure_modes=["seller_escalates", "deadline_imminent"],
        capabilities={"pressure_soft", "close_next"},
        guards={"avoid_mentioning_own_numbers"},
        tags={"bargaining", "aggressive"},
    ),
    Policy(
        policy_id="deescalate_tension",
        description="Bajar tensión y recuperar tono.",
        primary_when="Interacción tensa o defensiva.",
        hard_constraints="Evitar sarcasmo o presión adicional.",
        hard_constraints_rules=["avoid_reveal_own_numbers"],
        rag_query_template=(
            "Tácticas de desescalada en negociación presencial sin ceder de más."
        ),
        phase_hints=["recovery"],
        required_inputs=[{"key": "tone_signal", "op": "exists"}],
        target_slots=["rapport_signal"],
        expected_effects=["reduces_tension", "restores_cooperation"],
        failure_modes=["seller_hostile"],
        capabilities={"pressure_soft", "probe_open"},
        guards={"safe_when_tense", "avoid_mentioning_own_numbers"},
        tags={"deescalation", "safe_when_tense"},
    ),
    Policy(
        policy_id="close_with_conditions",
        description="Cerrar con condiciones concretas y recapitulación.",
        primary_when="Acuerdo cercano o hay consenso básico.",
        hard_constraints="No aceptar más de 10k total; dejar claro el siguiente paso.",
        hard_constraints_rules=["respect_batna", "avoid_reveal_own_numbers"],
        rag_query_template=(
            "Guía para cerrar condiciones claras y confirmar acuerdo." 
        ),
        phase_hints=["closing"],
        required_inputs=[{"key": "price_mentioned", "op": "true"}],
        target_slots=["price", "docs"],
        expected_effects=["agreement_next_step", "confirm_terms"],
        failure_modes=["price_over_limit", "missing_docs"],
        capabilities={"close_next"},
        guards={"requires_slot_complete", "avoid_mentioning_own_numbers"},
        tags={"closing"},
    ),
]


def list_policy_ids() -> List[str]:
    return [policy.policy_id for policy in POLICIES]


def safe_neutral_policy_id() -> str:
    ids = list_policy_ids()
    if "safe_neutral" in ids:
        return "safe_neutral"
    if "rapport_build" in ids:
        return "rapport_build"
    return ids[0] if ids else "safe_neutral"


def policy_catalog_text() -> str:
    lines = []
    for policy in POLICIES:
        phase_hints = ",".join(policy.phase_hints)
        lines.append(
            f"- {policy.policy_id}: {policy.description} | Cuándo: {policy.primary_when} | "
            f"Fases: {phase_hints} | Required: {policy.required_inputs} | "
            f"Target slots: {policy.target_slots} | Expected: {policy.expected_effects} | "
            f"Failure: {policy.failure_modes}"
        )
    return "\n".join(lines)


def policy_phase_catalog() -> dict[str, list[str]]:
    return {policy.policy_id: list(policy.phase_hints) for policy in POLICIES}


def get_policy(policy_id: str) -> Policy | None:
    for policy in POLICIES:
        if policy.policy_id == policy_id:
            return policy
    return None
