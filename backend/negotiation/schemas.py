# backend/negotiation/schemas.py
from __future__ import annotations

from typing import Dict, List, Literal, Set, TypedDict
InteractionHealth = Literal["stable", "tense", "stalled"]
RiskPosture = Literal["low", "mid", "high"]
PolicyOutcome = Literal["good", "neutral", "bad", ""]
ToneSignal = Literal["neutral", "friendly", "tense"]
IntentStatus = Literal["inactive", "active", "succeeded", "abandoned"]
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
    min_price_claimed: bool
    min_price_text: str
    price_firm: bool
    price_firm_text: str
    evidence_offered: bool
    evidence_text: str
    message_is_vague: bool
    tone_signal: ToneSignal
    tone_marker_hits: List[str]


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


def default_world_state() -> WorldState:
    return {
        "price_mentioned": False,
        "price_value": None,
        "deadline_claimed": False,
        "deadline_text": "",
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
        "min_price_claimed": False,
        "min_price_text": "",
        "price_firm": False,
        "price_firm_text": "",
        "evidence_offered": False,
        "evidence_text": "",
        "message_is_vague": False,
        "tone_signal": "neutral",
        "tone_marker_hits": [],
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
    }
