# backend/negotiation/schemas.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Set, TypedDict
InteractionHealth = Literal["stable", "tense", "stalled"]
RiskPosture = Literal["low", "mid", "high"]
PolicyOutcome = Literal["good", "neutral", "bad", ""]
ToneSignal = Literal["neutral", "friendly", "tense"]
EvidenceType = Literal[
    "PRICE",
    "DEADLINE",
    "URGENCY",
    "OTHER_BUYER",
    "CONCESSION",
    "DOCS",
    "MIN_PRICE",
    "FIRMNESS",
    "EVIDENCE_DOC",
    "BATNA",
    "TONE",
]
EvidenceSource = Literal["regex", "llm", "manual"]
IntentStatus = Literal["inactive", "active", "succeeded", "abandoned", "paused"]
IntentType = Literal[
    "info_extract",
    "relationship",
    "concession",
    "closing",
    "credibility_check",
]
CommitmentLevel = Literal["hard", "soft"]
StepKind = Literal[
    "probe_open",
    "probe_narrow",
    "request_evidence",
    "trade_incentive",
    "pressure_soft",
    "close_next",
]
NegotiationPhase = Literal["opening", "discovery", "bargaining", "closing", "recovery"]


class IntentSlot(TypedDict):
    value: object
    evidence: str
    confidence: float
    source: str


class IntentSlots(TypedDict):
    slots_required: List[str]
    slots_optional: List[str]
    slots_filled: Dict[str, IntentSlot]


class IntentStep(TypedDict):
    kind: StepKind
    target_slot: str
    success_if_filled: List[str]


class IntentState(TypedDict):
    status: IntentStatus
    intent_goal: str
    intent_type: IntentType
    steps: List[IntentStep]
    step_idx: int
    step_attempts: int
    max_attempts_per_step: int
    success_criteria: List[str]
    slots: IntentSlots
    confidence: float
    no_progress_turns: int
    slot_fill_count: int
    slot_fill_count_recent: int
    created_turn: int
    last_turn: int
    continue_until: str
    abandon_reasons: List[str]
    last_observation: str
    next_action_hint: str


class WorldState(TypedDict):
    price_mentioned: bool
    price_value: float | None
    deadline_claimed: bool
    deadline_text: str
    deadline_days: int | None
    deadline_kind: str
    other_buyer_claimed: bool
    other_buyer_text: str
    other_buyer_offer_price: float | None
    other_buyer_timing_text: str
    concession_made: bool
    concession_text: str
    docs_claimed: bool
    docs_types: List[str]
    batna_claimed: bool
    batna_text: str
    urgency_claimed: bool
    urgency_text: str
    urgency_reason: str
    min_price_claimed: bool
    min_price_text: str
    price_firm: bool
    price_firm_text: str
    evidence_offered: bool
    evidence_text: str
    message_is_vague: bool
    tone_signal: ToneSignal
    tone_confidence: float
    tone_marker_hits: List[str]
    conflict_markers: List[str]
    evidence_items: List["EvidenceItem"]
    world_state_meta: "WorldStateMeta"


class EvidenceItem(TypedDict):
    type: EvidenceType
    text: str
    value: Any | None
    source: EvidenceSource
    confidence: float
    turn_idx: int | None
    raw: Dict[str, Any] | None


class WorldStateMeta(TypedDict):
    last_update_source: Literal["regex", "llm", "mixed"]
    evidence_confidence_min: float
    updated_fields: List[str]
    turn_idx: int | None


class BeliefReason(TypedDict):
    weight: float
    confidence: float
    evidence: str


class BeliefStance(TypedDict):
    deal_feasibility: float
    seller_flexibility: float


class BeliefDynamics(TypedDict):
    interaction_health: InteractionHealth
    last_update_evidence: str


class BeliefToM(TypedDict):
    seller_goals: List[str]
    seller_tactics: List[str]
    seller_belief_about_me: List[str]
    confidence: float


class BeliefState(TypedDict):
    stance: BeliefStance
    reasons: Dict["ReasonKey", BeliefReason]
    hypotheses: List[str]
    dynamics: BeliefDynamics
    tom: BeliefToM


class PolicyDecision(TypedDict):
    policy_id: str
    reason: str
    micro_goal: str
    risk_posture: RiskPosture
    capabilities: Set[str] | None
    why_short: str
    inputs_used: List[str]


class IntentHint(TypedDict):
    intent_active: bool
    intent_goal: str
    intent_type: str
    step_kind: str
    target_slot: str
    next_action_hint: str
    slots_missing: List[str]
    slots_filled_summary: str
    commitment_level: CommitmentLevel


class PhaseState(TypedDict):
    phase: NegotiationPhase
    confidence: float
    reasons: List[str]
    last_updated_turn: int


ReasonKey = Literal[
    "price_signal",
    "deadline_signal",
    "other_buyer_signal",
    "concession_signal",
    "docs_signal",
    "tone_signal",
]


class ProgressState(TypedDict):
    last_executed_policy_id: str
    last_executed_policy_outcome: PolicyOutcome
    last_chosen_policy_id: str
    policy_last_outcome: Dict[str, PolicyOutcome]
    policy_attempts: Dict[str, int]
    loop_flags: List[str]
    turns_in_same_mode: int
    intent_state: IntentState
    phase_state: PhaseState


def default_world_state() -> WorldState:
    return {
        "price_mentioned": False,
        "price_value": None,
        "deadline_claimed": False,
        "deadline_text": "",
        "deadline_days": None,
        "deadline_kind": "unknown",
        "other_buyer_claimed": False,
        "other_buyer_text": "",
        "other_buyer_offer_price": None,
        "other_buyer_timing_text": "",
        "concession_made": False,
        "concession_text": "",
        "docs_claimed": False,
        "docs_types": [],
        "batna_claimed": False,
        "batna_text": "",
        "urgency_claimed": False,
        "urgency_text": "",
        "urgency_reason": "",
        "min_price_claimed": False,
        "min_price_text": "",
        "price_firm": False,
        "price_firm_text": "",
        "evidence_offered": False,
        "evidence_text": "",
        "message_is_vague": False,
        "tone_signal": "neutral",
        "tone_confidence": 0.0,
        "tone_marker_hits": [],
        "conflict_markers": [],
        "evidence_items": [],
        "world_state_meta": {
            "last_update_source": "regex",
            "evidence_confidence_min": 0.6,
            "updated_fields": [],
            "turn_idx": None,
        },
    }


def default_belief_state() -> BeliefState:
    return {
        "stance": {
            "deal_feasibility": 0.5,
            "seller_flexibility": 0.5,
        },
        "reasons": {},
        "hypotheses": [],
        "dynamics": {
            "interaction_health": "stable",
            "last_update_evidence": "",
        },
        "tom": {
            "seller_goals": [],
            "seller_tactics": [],
            "seller_belief_about_me": [],
            "confidence": 0.4,
        },
    }


def default_progress_state() -> ProgressState:
    return {
        "last_executed_policy_id": "",
        "last_executed_policy_outcome": "",
        "last_chosen_policy_id": "",
        "policy_last_outcome": {},
        "policy_attempts": {},
        "loop_flags": [],
        "turns_in_same_mode": 0,
        "intent_state": default_intent_state(),
        "phase_state": {
            "phase": "opening",
            "confidence": 0.6,
            "reasons": [],
            "last_updated_turn": 0,
        },
    }


def default_intent_state() -> IntentState:
    return {
        "status": "inactive",
        "intent_goal": "",
        "intent_type": "info_extract",
        "steps": [],
        "step_idx": 0,
        "step_attempts": 0,
        "max_attempts_per_step": 2,
        "success_criteria": [],
        "slots": {
            "slots_required": [],
            "slots_optional": [],
            "slots_filled": {},
        },
        "confidence": 0.0,
        "no_progress_turns": 0,
        "slot_fill_count": 0,
        "slot_fill_count_recent": 0,
        "created_turn": 0,
        "last_turn": 0,
        "continue_until": "",
        "abandon_reasons": [],
        "last_observation": "",
        "next_action_hint": "",
    }


def default_policy_decision() -> PolicyDecision:
    return {
        "policy_id": "rapport_build",
        "reason": "Fallback seguro para mantener buen clima.",
        "micro_goal": "Mantener tono cordial y abrir espacio para información útil.",
        "risk_posture": "low",
        "capabilities": None,
        "why_short": "",
        "inputs_used": [],
    }
