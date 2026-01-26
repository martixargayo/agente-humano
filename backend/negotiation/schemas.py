# backend/negotiation/schemas.py
from __future__ import annotations

from typing import Dict, List, Literal, TypedDict
InteractionHealth = Literal["stable", "tense", "stalled"]
RiskPosture = Literal["low", "mid", "high"]
PolicyOutcome = Literal["good", "neutral", "bad", ""]


class WorldState(TypedDict):
    price_mentioned: bool
    price_value: float | None
    deadline_claimed: bool
    deadline_text: str
    other_buyer_claimed: bool
    concession_made: bool
    concession_text: str
    docs_claimed: bool
    docs_types: List[str]
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
    reasons: Dict[str, BeliefReason]
    hypotheses: List[str]
    dynamics: BeliefDynamics
    tom: BeliefToM


class PolicyDecision(TypedDict):
    policy_id: str
    reason: str
    micro_goal: str
    risk_posture: RiskPosture


class ProgressState(TypedDict):
    last_policy_id: str
    last_policy_outcome: PolicyOutcome
    policy_attempts: Dict[str, int]
    loop_flags: List[str]
    turns_in_same_mode: int


def default_world_state() -> WorldState:
    return {
        "price_mentioned": False,
        "price_value": None,
        "deadline_claimed": False,
        "deadline_text": "",
        "other_buyer_claimed": False,
        "concession_made": False,
        "concession_text": "",
        "docs_claimed": False,
        "docs_types": [],
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
        "last_policy_id": "",
        "last_policy_outcome": "",
        "policy_attempts": {},
        "loop_flags": [],
        "turns_in_same_mode": 0,
    }


def default_policy_decision() -> PolicyDecision:
    return {
        "policy_id": "rapport_build",
        "reason": "Fallback seguro para mantener buen clima.",
        "micro_goal": "Mantener tono cordial y abrir espacio para información útil.",
        "risk_posture": "low",
    }
