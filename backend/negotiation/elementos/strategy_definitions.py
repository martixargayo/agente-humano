import os
from dataclasses import dataclass
from typing import List, Literal, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, confloat, conlist

from ..schemas import NegotiationPhase, RequiredBelief, RequiredInput

PHASES = ("climate", "interests", "options", "adjust", "formalize")
PHASE_CLIMATE = "climate"
PHASE_INTERESTS = "interests"
PHASE_OPTIONS = "options"
PHASE_ADJUST = "adjust"
PHASE_FORMALIZE = "formalize"
PHASE_ORDER: list[NegotiationPhase] = ["climate", "interests", "options", "adjust", "formalize"]
PHASE_INDEX: dict[NegotiationPhase, int] = {phase: idx for idx, phase in enumerate(PHASE_ORDER)}

LEGACY_PHASE_LITERAL = Literal["opening", "discovery", "bargaining", "closing", "recovery"]
PHASE_LITERAL = Literal["climate", "interests", "options", "adjust", "formalize"]
REASON_PREFIXES = {"world", "belief", "intent", "history"}
RISK_POSTURES = ("low", "mid", "high")


@dataclass(frozen=True)
class SuccessCond:
    kind: Literal["slot_filled", "world_flag_true", "belief_flag_eq"]
    key: str
    value: object | None = None


@dataclass(frozen=True)
class PolicyStep:
    kind: str
    target_slot: str
    micro_goal: str
    next_action_hint: str
    success_if: List[SuccessCond]


@dataclass(frozen=True)
class PolicyPlan:
    slots_required: List[str]
    steps: List[PolicyStep]
    max_attempts_per_step: int = 2
    max_turns_total: int = 6
    no_progress_turns_limit: int = 2


class PhaseSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["world", "belief", "intent", "history"]
    key: str = Field(max_length=48)
    value: str = Field(max_length=120)


class PlannerStepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_idx: int = Field(default=0, ge=0)
    goal: str = Field(default="", max_length=160)
    success_criteria: conlist(str, max_length=4) = Field(default_factory=list)
    instruction: str = Field(default="", max_length=260)


class PlannerActivePlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(default="", max_length=40)
    current_step_idx: int = Field(default=0, ge=0)
    context_digest: str = Field(default="", max_length=220)
    steps: conlist(PlannerStepModel, min_length=2, max_length=5)


class PhasePolicyDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: PHASE_LITERAL | LEGACY_PHASE_LITERAL
    confidence: confloat(ge=0.0, le=1.0) = 0.6
    recovery_mode: bool = False
    reasons: conlist(str, max_length=6) = Field(default_factory=list)
    policy_id: str = ""
    reason: str = Field(default="", max_length=180)
    micro_goal: str = Field(default="", max_length=140)
    risk_posture: Literal["low", "mid", "high"] = Field(default="low")
    why_short: str = Field(default="", max_length=140)
    active_plan: PlannerActivePlanModel


class PlannerV2StepModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step_idx: int = Field(default=0, ge=0)
    intent_id: str = Field(default="", max_length=64)
    goal: str = Field(default="", max_length=220)
    instruction: str = Field(default="", max_length=320)
    ask_slots: conlist(str, max_length=1) = Field(default_factory=list)
    success_criteria: conlist(str, max_length=5) = Field(default_factory=list)
    stop_conditions: conlist(str, max_length=5) = Field(default_factory=list)


class PlannerV2ActivePlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(default="", max_length=64)
    current_step_idx: int = Field(default=0, ge=0)
    context_digest: str = Field(default="", max_length=320)
    required_intents: conlist(str, max_length=8) = Field(default_factory=list)
    covered_intents: conlist(str, max_length=8) = Field(default_factory=list)
    steps: conlist(PlannerV2StepModel, min_length=2, max_length=5)


class PlannerV2ExecutorInstructionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_id: str = Field(default="", max_length=64)
    step_idx: int = Field(default=0, ge=0)
    instruction: str = Field(default="", max_length=320)
    ask_slots: conlist(str, max_length=1) = Field(default_factory=list)
    must_avoid: conlist(str, max_length=8) = Field(default_factory=list)
    max_questions_per_turn: int = Field(default=1, ge=0, le=1)
    language: Literal["es"] = "es"
    style_id: Literal["psyplay_compact"] = "psyplay_compact"


class PlannerV2DecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["planner_v2"] = "planner_v2"
    phase: PHASE_LITERAL
    recovery_mode: bool = False
    policy_id: str = ""
    active_plan: PlannerV2ActivePlanModel
    executor_instruction: PlannerV2ExecutorInstructionModel


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
    plan: Optional[PolicyPlan] = None
    required_beliefs: List[RequiredBelief] | None = None


def _policy(
    policy_id: str,
    phase_hints: list[NegotiationPhase],
    *,
    tags: set[str] | None = None,
    guards: set[str] | None = None,
    required_inputs: list[RequiredInput] | None = None,
    target_slots: list[str] | None = None,
    expected_effects: list[str] | None = None,
    capabilities: set[str] | None = None,
    plan: PolicyPlan | None = None,
    required_beliefs: list[RequiredBelief] | None = None,
) -> Policy:
    return Policy(
        policy_id=policy_id,
        description=policy_id.replace("_", " "),
        primary_when="policy_catalog_v2",
        hard_constraints="seguir reglas universales",
        hard_constraints_rules=["keep_tone_respectful"],
        rag_query_template=policy_id,
        phase_hints=phase_hints,
        required_inputs=required_inputs or [],
        target_slots=target_slots or [],
        expected_effects=expected_effects or [],
        failure_modes=["no_progress"],
        capabilities=capabilities or {"probe_open"},
        guards=guards or set(),
        tags=tags or set(),
        plan=plan,
        required_beliefs=required_beliefs,
    )


POLICIES: List[Policy] = [
    _policy("safe_neutral", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}, target_slots=["rapport_signal"]),
    _policy("reflect_and_validate", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "deescalation", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}, required_beliefs=[{"key": "universal.dynamics.interaction_health", "op": "in", "value": ["tense", "stalled"]}]),
    _policy("summarize_and_align", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "recovery_ok"}),
    _policy("clarify_missing_info", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "recovery_ok"}, plan=PolicyPlan(slots_required=["world_buckets.context"], max_attempts_per_step=2, max_turns_total=3, no_progress_turns_limit=1, steps=[PolicyStep(kind="ask_open", target_slot="world_buckets.context", micro_goal="identificar missing info", next_action_hint="Haz 1 pregunta abierta sobre el punto más confuso.", success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")]), PolicyStep(kind="ask_targeted", target_slot="world_buckets.context", micro_goal="concretar datos", next_action_hint="Formula 1–2 preguntas cerradas (sí/no o A/B).", success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")])])),
    _policy("set_process_rules", ["climate", "interests", "options", "adjust"], tags={"universal", "recovery_ok"}),
    _policy("meta_negotiation_reset", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "deescalation", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}),
    _policy("boundary_and_respect", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("repair_loop_structured_choice", ["climate", "interests", "options", "adjust", "formalize"], tags={"universal", "recovery_ok"}, guards={"safe_when_tense"}, plan=PolicyPlan(slots_required=["gate.loop_flags"], max_attempts_per_step=2, max_turns_total=3, no_progress_turns_limit=1, steps=[PolicyStep(kind="reframe_choice", target_slot="gate.loop_flags", micro_goal="ofrecer dos rutas", next_action_hint="Presenta Opción A y Opción B (ambas razonables).", success_if=[SuccessCond(kind="slot_filled", key="gate.loop_flags")]), PolicyStep(kind="ask_targeted", target_slot="world_buckets.context", micro_goal="obtener nueva información", next_action_hint="Haz 1 pregunta concreta según la opción elegida.", success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")])])),
    _policy("tone_deescalate", ["climate", "interests", "options", "adjust", "formalize"], tags={"deescalation", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}, required_beliefs=[{"key": "planner_signals.conflict_risk", "op": "gte", "value": 0.6}]),
    _policy("trust_micro_reciprocity", ["climate", "interests"], tags={"universal", "recovery_ok"}, guards={"avoid_mentioning_own_numbers"}),
    _policy("rapport_and_legitimacy", ["climate"], tags={"climate", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}),
    _policy("separate_people_from_problem", ["climate"], tags={"climate", "deescalation", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("diagnose_resistance", ["climate"], tags={"climate", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("communication_clean_channel", ["climate"], tags={"climate", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("permission_to_probe", ["climate"], tags={"climate", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("acknowledge_and_bridge", ["climate"], tags={"climate", "recovery_ok", "deescalation"}, guards={"safe_when_tense"}),
    _policy("recovery_mode_entry", ["climate"], tags={"climate", "deescalation", "recovery_ok", "safe_when_tense"}, guards={"safe_when_tense"}),
    _policy("exit_climate_check", ["climate"], tags={"climate", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("discover_interests_open", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense", "avoid_mentioning_own_numbers"}, capabilities={"probe_open", "probe_narrow"}),
    _policy("map_priorities_rank", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("surface_constraints_nonnegotiables", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"probe_open", "probe_narrow"}),
    _policy("batna_probe_soft", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense", "avoid_mentioning_own_numbers"}),
    _policy("criteria_seed_objective", ["interests"], tags={"interests", "recovery_ok", "legitimacy"}, guards={"safe_when_tense"}),
    _policy("risk_and_trust_probe", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"probe_open", "probe_narrow"}),
    _policy("time_pressure_probe", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense", "requires_deadline_claim"}, required_inputs=[{"key": "deadline_claimed", "op": "true"}]),
    _policy("leverage_claim_probe", ["interests"], tags={"interests", "recovery_ok", "credibility"}, guards={"safe_when_tense", "requires_other_buyer_claimed"}, required_inputs=[{"key": "other_buyer_claimed", "op": "true"}]),
    _policy("request_evidence_if_claimed", ["interests"], tags={"interests", "recovery_ok", "credibility"}, guards={"safe_when_tense"}, required_inputs=[{"key": "evidence_relevant_claimed", "op": "true"}], capabilities={"request_evidence"}),
    _policy("credibility_probe_soft", ["interests"], tags={"interests", "recovery_ok", "credibility"}, guards={"safe_when_tense"}),
    _policy("open_points_register", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("phase_exit_to_options", ["interests"], tags={"interests", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("generate_options_batch", ["options"], tags={"options", "value_create"}, guards={"requires_not_recovery"}, capabilities={"option_generate"}),
    _policy("package_deal_builder", ["options"], tags={"options", "value_create"}, guards={"requires_not_recovery"}, capabilities={"option_package"}),
    _policy("tradeoff_if_then", ["options", "adjust"], tags={"tradeoff", "value_create"}, guards={"avoid_mentioning_own_numbers"}, capabilities={"trade_incentive"}),
    _policy("offer_meso_equivalents", ["options"], tags={"options", "value_create"}, guards={"requires_not_recovery"}, capabilities={"option_generate"}),
    _policy("expand_pie_non_monetary", ["options"], tags={"options", "value_create"}, guards={"requires_not_recovery"}, capabilities={"option_generate"}),
    _policy("criteria_based_optioning", ["options"], tags={"options", "legitimacy"}, guards={"requires_not_recovery"}),
    _policy("pre_mortem_option_risks", ["options"], tags={"options", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("preference_elicitation_fast", ["options"], tags={"options"}, guards={"requires_not_recovery"}),
    _policy("option_to_adjust_bridge", ["options"], tags={"options"}, guards={"requires_not_recovery"}),
    _policy("return_to_interests_if_stuck", ["options"], tags={"options", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("concession_protocol_quid_pro_quo", ["adjust"], tags={"adjust", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, capabilities={"trade_incentive"}),
    _policy("legitimacy_push_objective_standard", ["adjust"], tags={"adjust"}, guards={"avoid_mentioning_own_numbers"}, capabilities={"reframe", "pressure_soft"}),
    _policy("anchor_deflection_reframe", ["adjust"], tags={"adjust"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}], capabilities={"reframe"}),
    _policy("counter_anchor_soft", ["adjust"], tags={"adjust", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}], capabilities={"pressure_soft"}),
    _policy("bracketing_range_explore", ["adjust"], tags={"adjust", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}]),
    _policy("handle_objection_to_condition", ["adjust"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"probe_narrow", "trade_incentive"}),
    _policy("manage_time_pressure_no_panic", ["adjust"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}, required_inputs=[{"key": "deadline_claimed", "op": "true"}], capabilities={"probe_narrow", "deescalate"}),
    _policy("deadline_mirror_verify", ["adjust"], tags={"adjust", "recovery_ok", "credibility"}, guards={"safe_when_tense"}, required_inputs=[{"key": "deadline_claimed", "op": "true"}], capabilities={"request_evidence"}),
    _policy("resolve_contradiction_protocol", ["adjust"], tags={"adjust", "recovery_ok", "credibility"}, guards={"safe_when_tense"}, capabilities={"request_evidence", "clarify"}),
    _policy("credibility_test_structured", ["adjust"], tags={"adjust", "recovery_ok", "credibility"}, guards={"safe_when_tense", "avoid_mentioning_own_numbers"}, required_inputs=[{"key": "other_buyer_claimed", "op": "true"}], capabilities={"request_evidence", "probe_narrow"}, plan=PolicyPlan(slots_required=["world_buckets.context", "world_buckets.context"], steps=[PolicyStep(kind="request_evidence", target_slot="world_buckets.context", micro_goal="Pedir evidencia concreta de la oferta.", next_action_hint="Solicita dato verificable (condiciones, timing, prueba).", success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")]), PolicyStep(kind="probe_narrow", target_slot="world_buckets.context", micro_goal="Aclarar detalles del otro comprador.", next_action_hint="Pregunta por términos, tiempos y condiciones.", success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")])])),
    _policy("calibrate_walkaway_principled", ["adjust"], tags={"adjust", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, capabilities={"boundary", "pressure_soft"}),
    _policy("micro_commitment_next_step", ["adjust", "formalize"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"close_next"}),
    _policy("deal_readiness_check", ["adjust"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("open_points_closeout", ["adjust"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}, required_inputs=[{"key": "open_points_present", "op": "true"}], capabilities={"clarify", "close_next"}),
    _policy("aggressive_contrast_choice", ["adjust"], tags={"adjust", "aggressive"}, guards={"requires_not_recovery"}, capabilities={"pressure_soft"}),
    _policy("strategic_silence_prompt", ["adjust"], tags={"adjust", "recovery_ok"}, guards={"safe_when_tense"}),
    _policy("formalize_recap_confirm", ["formalize"], tags={"formalize", "recovery_ok"}, guards={"requires_slot_complete", "safe_when_tense"}, capabilities={"close_next"}, plan=PolicyPlan(slots_required=["agreement_recap_confirmed"], max_attempts_per_step=2, max_turns_total=3, no_progress_turns_limit=1, steps=[PolicyStep(kind="close_recap", target_slot="agreement_recap_confirmed", micro_goal="recap", next_action_hint="Recapitula SOLO lo acordado en 4–6 bullets.", success_if=[SuccessCond(kind="slot_filled", key="agreement_recap_confirmed")]), PolicyStep(kind="close_next_step", target_slot="agreement_next_step", micro_goal="siguiente paso", next_action_hint="Propón 1 siguiente paso y pide confirmación.", success_if=[SuccessCond(kind="slot_filled", key="agreement_next_step")])])),
    _policy("recap_terms_confirm", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"close_next"}),
    _policy("document_terms_request", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"request_evidence"}),
    _policy("confirm_next_steps_logistics", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"close_next"}),
    _policy("confirm_payment_and_transfer", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"close_next"}),
    _policy("confirm_risk_and_warranty_terms", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, capabilities={"close_next"}),
    _policy("confirm_open_points_back_to_adjust", ["formalize", "adjust"], tags={"formalize", "recovery_ok"}, guards={"safe_when_tense"}, required_inputs=[{"key": "open_points_present", "op": "true"}]),
    _policy("close_graciously_leave_door_open", ["formalize", "climate"], tags={"formalize", "recovery_ok", "deescalation"}, guards={"safe_when_tense"}, capabilities={"deescalate"}),

    # Legacy aliases (compat temporal para tests/runtime antiguos)
    _policy("rapport_build", ["climate"], tags={"deescalation", "safe_when_tense", "recovery_ok"}, guards={"safe_when_tense", "avoid_mentioning_own_numbers"}),
    _policy("info_extract_critical", ["interests", "climate"], tags={"bargaining"}, guards={"avoid_mentioning_own_numbers", "safe_when_tense"}, capabilities={"probe_open", "probe_narrow"}),
    _policy(
        "test_credibility",
        ["interests", "climate"],
        tags={"credibility_check"},
        guards={"safe_when_tense", "avoid_mentioning_own_numbers"},
        required_inputs=[{"key": "other_buyer_claimed", "op": "true"}],
        capabilities={"request_evidence", "probe_narrow"},
        plan=PolicyPlan(
            slots_required=["world_buckets.context", "world_buckets.context"],
            steps=[
                PolicyStep(
                    kind="request_evidence",
                    target_slot="world_buckets.context",
                    micro_goal="Pedir evidencia concreta de la otra oferta.",
                    next_action_hint="Solicita datos verificables de la supuesta oferta.",
                    success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")],
                ),
                PolicyStep(
                    kind="probe_narrow",
                    target_slot="world_buckets.context",
                    micro_goal="Aclarar detalles del otro comprador.",
                    next_action_hint="Pregunta por términos, tiempos y condiciones del comprador.",
                    success_if=[SuccessCond(kind="slot_filled", key="world_buckets.context")],
                ),
            ],
        ),
    ),
    _policy("delay_price_discussion", ["interests", "climate"], tags={"bargaining"}, guards={"avoid_mentioning_own_numbers", "requires_price_not_mentioned"}, required_inputs=[{"key": "price_mentioned", "op": "exists"}]),
    _policy("challenge_anchor_indirect", ["adjust"], tags={"bargaining", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}], capabilities={"pressure_soft"}),
    _policy("tradeoff_offer", ["adjust"], tags={"bargaining"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}], capabilities={"trade_incentive"}),
    _policy("hold_position", ["adjust"], tags={"bargaining", "aggressive"}, guards={"avoid_mentioning_own_numbers"}, required_inputs=[{"key": "price_mentioned", "op": "true"}], capabilities={"pressure_soft", "close_next"}),
    _policy("deescalate_tension", ["climate"], tags={"deescalation", "safe_when_tense", "recovery_ok"}, guards={"safe_when_tense", "avoid_mentioning_own_numbers"}, required_inputs=[{"key": "tone_signal", "op": "exists"}], required_beliefs=[{"key": "planner_signals.conflict_risk", "op": "gte", "value": 0.6}], capabilities={"pressure_soft", "probe_open"}),
]
