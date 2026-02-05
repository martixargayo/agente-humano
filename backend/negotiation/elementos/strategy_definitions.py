import os
from dataclasses import dataclass
from typing import List, Literal, Set

from pydantic import BaseModel, ConfigDict, Field, confloat, conlist

from ..schemas import NegotiationPhase, RequiredInput

PHASES = ("opening", "discovery", "bargaining", "closing", "recovery")
PHASE_OPENING = "opening"
PHASE_DISCOVERY = "discovery"
PHASE_BARGAINING = "bargaining"
PHASE_CLOSING = "closing"
PHASE_RECOVERY = "recovery"
PHASE_ORDER: list[NegotiationPhase] = ["opening", "discovery", "bargaining", "closing"]
PHASE_INDEX: dict[NegotiationPhase, int] = {phase: idx for idx, phase in enumerate(PHASE_ORDER)}

PHASE_LITERAL = Literal["opening", "discovery", "bargaining", "closing", "recovery"]
REASON_PREFIXES = {"world", "belief", "intent", "history"}
RISK_POSTURES = ("low", "mid", "high")


class PhaseSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["world", "belief", "intent", "history"]
    key: str = Field(max_length=48)
    value: str = Field(max_length=120)


class PhasePolicyDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: PHASE_LITERAL
    confidence: confloat(ge=0.0, le=1.0) = 0.6
    reasons: conlist(str, max_length=8) = Field(default_factory=list)
    signals: conlist(PhaseSignal, max_length=8) = Field(default_factory=list)
    alternatives: conlist(PHASE_LITERAL, max_length=3) = Field(default_factory=list)
    policy_id: str = ""
    reason: str = Field(default="", max_length=180)
    micro_goal: str = Field(default="", max_length=140)
    risk_posture: Literal["low", "mid", "high"] = Field(default="low")
    why_short: str = Field(default="", max_length=140)
    inputs_used: list[str] = Field(default_factory=list, max_length=8)


INTENT_TYPES = (
    "relationship",
    "closing",
    "concession",
    "credibility_check",
    "info_extract",
)

INTENT_CONTRACTS = {
    "credibility_check": {
        "goal": (
            "Verificar si el 'otro comprador' es real y extraer detalles verificables sin revelar "
            "mi límite."
        ),
        "required": ["other_buyer_details", "evidence_offered"],
        "optional": ["deadline_real", "price_firm"],
        "success_criteria": ["slots_required_complete", "evidence_offered"],
    },
    "closing": {
        "goal": "Confirmar si el precio es firme y definir condiciones mínimas antes de cerrar.",
        "required": ["price", "price_firm"],
        "optional": ["concession", "docs"],
        "success_criteria": ["slots_required_complete", "firm_price_detected"],
    },
    "concession": {
        "goal": "Aclarar concesiones reales y margen sin comprometerse.",
        "required": ["concession"],
        "optional": ["price", "seller_min_acceptable"],
        "success_criteria": ["slots_required_complete"],
    },
    "relationship": {
        "goal": "Bajar tensión y restablecer señales de cooperación.",
        "required": ["tone_signal"],
        "optional": ["rapport_signal"],
        "success_criteria": ["slots_required_complete"],
    },
    "info_extract": {
        "goal": (
            "Descubrir la urgencia real y la alternativa del vendedor (BATNA) para calibrar margen."
        ),
        "required": ["seller_batna", "seller_urgency_reason"],
        "optional": ["seller_min_acceptable", "price_firm"],
        "success_criteria": ["slots_required_complete"],
    },
}

KNOWN_SUCCESS_CRITERIA = {
    "slots_required_complete",
    "firm_price_detected",
    "evidence_offered",
}

INTENT_STEP_SEQUENCE = [
    "probe_open",
    "probe_narrow",
    "request_evidence",
    "trade_incentive",
    "pressure_soft",
]

INTENT_CLOSE_STEP = {
    "kind": "close_next",
    "target_slot": "",
    "success_if_filled": [],
}

PIVOT_KIND_MAPPING = {
    "probe_open": "open",
    "probe_narrow": "narrow",
    "request_evidence": "evidence",
    "trade_incentive": "incentive",
    "pressure_soft": "soft_pressure",
    "close_next": "narrow",
}

OPEN_FACTOR_SIGNALS = (
    "price_mentioned",
    "docs_claimed",
    "deadline_claimed",
    "other_buyer_claimed",
    "batna_claimed",
    "urgency_claimed",
    "min_price_claimed",
    "price_firm",
    "evidence_offered",
)

URGENCY_DEADLINE_DAYS = {0, 1, 2}

INTENT_WEIGHT_SLOTS = float(os.getenv("INTENT_WEIGHT_SLOTS", "0.6"))
INTENT_WEIGHT_OPEN_FACTORS = float(os.getenv("INTENT_WEIGHT_OPEN_FACTORS", "0.3"))
INTENT_WEIGHT_UNCERTAINTY = float(os.getenv("INTENT_WEIGHT_UNCERTAINTY", "0.4"))
INTENT_COST_TENSION = float(os.getenv("INTENT_COST_TENSION", "0.7"))
INTENT_COST_REPEAT = float(os.getenv("INTENT_COST_REPEAT", "0.4"))
INTENT_COST_URGENCY = float(os.getenv("INTENT_COST_URGENCY", "0.6"))
INTENT_START_UTILITY_THRESHOLD = float(os.getenv("INTENT_START_UTILITY_THRESHOLD", "1.0"))
INTENT_FIRMNESS_REPLAN_THRESHOLD = float(os.getenv("INTENT_FIRMNESS_REPLAN_THRESHOLD", "0.6"))
INTENT_MAX_ATTEMPTS_PER_STEP = int(os.getenv("INTENT_MAX_ATTEMPTS_PER_STEP", "2"))
INTENT_CONFIDENCE_DECAY = float(os.getenv("INTENT_CONFIDENCE_DECAY", "0.1"))
INTENT_MAX_TURNS = int(os.getenv("INTENT_MAX_TURNS", "6"))
INTENT_NO_PROGRESS_ABORT_TURNS = int(os.getenv("INTENT_NO_PROGRESS_ABORT_TURNS", "2"))


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
        rag_query_template=("Guía para cerrar condiciones claras y confirmar acuerdo."),
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
