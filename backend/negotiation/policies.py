# backend/negotiation/policies.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set


@dataclass(frozen=True)
class Policy:
    policy_id: str
    description: str
    primary_when: str
    hard_constraints: str
    rag_query_template: str
    phase_hint: str | None = None
    capabilities: Set[str] | None = None
    guards: Set[str] | None = None


POLICIES: List[Policy] = [
    Policy(
        policy_id="rapport_build",
        description="Construir clima cordial y reducir fricciones.",
        primary_when="Inicio de la interacción o clima frío.",
        hard_constraints="No presionar el precio ni confrontar directamente.",
        rag_query_template=(
            "Tácticas para generar rapport sin perder objetivo en una negociación presencial."
        ),
        phase_hint="1",
        capabilities={"probe_open"},
        guards={"safe_when_tense"},
    ),
    Policy(
        policy_id="info_extract_critical",
        description="Extraer información crítica del coche y del vendedor.",
        primary_when="Faltan datos clave o el vendedor es ambiguo.",
        hard_constraints="No comprometerse con precio aún.",
        rag_query_template=(
            "Preguntas y técnicas para descubrir información crítica sin sonar interrogatorio."
        ),
        phase_hint="2",
        capabilities={"probe_open", "probe_narrow"},
        guards={"avoid_price_numbers", "safe_when_tense"},
    ),
    Policy(
        policy_id="test_credibility",
        description="Poner a prueba consistencia o veracidad del vendedor.",
        primary_when="Se detectan inconsistencias, urgencias o excusas.",
        hard_constraints="Evitar acusaciones directas; mantener tono calmado.",
        rag_query_template=(
            "Cómo contrastar credibilidad con preguntas indirectas y señales suaves."
        ),
        phase_hint="2",
        capabilities={"request_evidence", "probe_narrow"},
        guards=set(),
    ),
    Policy(
        policy_id="delay_price_discussion",
        description="Posponer el precio para mantener control del ritmo.",
        primary_when="El vendedor quiere cerrar precio muy pronto.",
        hard_constraints="No discutir cifras ni anclas numéricas propias.",
        rag_query_template=(
            "Tácticas para aplazar precio y reconducir a información o valor."
        ),
        phase_hint="2",
        capabilities={"probe_open"},
        guards={"avoid_price_numbers"},
    ),
    Policy(
        policy_id="challenge_anchor_indirect",
        description="Cuestionar el ancla de precio sin confrontar.",
        primary_when="Hay ancla alta o presión por precio.",
        hard_constraints="No revelar límite 10k ni alternativa explícita.",
        rag_query_template=(
            "Formas indirectas de desafiar un precio alto y abrir espacio."
        ),
        phase_hint="4",
        capabilities={"pressure_soft"},
        guards=set(),
    ),
    Policy(
        policy_id="tradeoff_offer",
        description="Proponer intercambio: precio vs. condiciones o extras.",
        primary_when="Hay margen para concesiones recíprocas.",
        hard_constraints="No ceder gratis; siempre pedir algo a cambio.",
        rag_query_template=(
            "Cómo formular trade-offs claros que mantengan control del valor."
        ),
        phase_hint="4",
        capabilities={"trade_incentive"},
        guards=set(),
    ),
    Policy(
        policy_id="hold_position",
        description="Mantener postura firme sin escalar conflicto.",
        primary_when="Necesitas sostener un límite o no moverte más.",
        hard_constraints="No sonar ultimátum ni romper la relación.",
        rag_query_template=(
            "Frases breves para mantener posición y seguir negociando."
        ),
        phase_hint="4",
        capabilities={"pressure_soft", "close_next"},
        guards=set(),
    ),
    Policy(
        policy_id="deescalate_tension",
        description="Bajar tensión y recuperar tono.",
        primary_when="Interacción tensa o defensiva.",
        hard_constraints="Evitar sarcasmo o presión adicional.",
        rag_query_template=(
            "Tácticas de desescalada en negociación presencial sin ceder de más."
        ),
        phase_hint="1",
        capabilities={"pressure_soft", "probe_open"},
        guards={"safe_when_tense"},
    ),
    Policy(
        policy_id="close_with_conditions",
        description="Cerrar con condiciones concretas y recapitulación.",
        primary_when="Acuerdo cercano o hay consenso básico.",
        hard_constraints="No aceptar más de 10k total; dejar claro el siguiente paso.",
        rag_query_template=(
            "Guía para cerrar condiciones claras y confirmar acuerdo." 
        ),
        phase_hint="5",
        capabilities={"close_next"},
        guards={"requires_slot_complete"},
    ),
]


def list_policy_ids() -> List[str]:
    return [policy.policy_id for policy in POLICIES]


def policy_catalog_text() -> str:
    lines = []
    for policy in POLICIES:
        lines.append(
            f"- {policy.policy_id}: {policy.description} | Cuándo: {policy.primary_when}"
        )
    return "\n".join(lines)


def get_policy(policy_id: str) -> Policy | None:
    for policy in POLICIES:
        if policy.policy_id == policy_id:
            return policy
    return None
