from __future__ import annotations

from typing import Any

WORLD_SCHEMA_VERSIONS = {"v1", "v2"}
BELIEF_SCHEMA_VERSIONS = {"v1", "v2"}

TONE_ENUM = {"neutral", "warm", "cold", "tense", "hostile", "collaborative", "defensive", "assertive", "uncertain", "other"}
SENTIMENT_ENUM = {"negative", "neutral", "positive", "mixed", "other"}
AROUSAL_ENUM = {"low", "medium", "high", "other"}
INTENT_ACT_ENUM = {"ask", "inform", "offer", "counter", "accept", "reject", "clarify", "delay", "commit", "withdraw", "other"}

COMMITMENT_TYPE_ENUM = {"promise", "condition", "deadline", "documentation", "payment", "delivery", "inspection", "warranty", "other"}
COMMITMENT_STATUS_ENUM = {"claimed", "unverified", "verified", "contradicted", "fulfilled", "broken"}
OFFER_SIDE_ENUM = {"buyer", "seller"}
OFFER_KIND_ENUM = {"price", "bundle", "condition", "tradeoff"}
OFFER_FIRMNESS_ENUM = {"soft", "medium", "hard"}
OFFER_STATUS_ENUM = {"proposed", "active", "withdrawn", "accepted", "rejected"}
CONSTRAINT_SIDE_ENUM = {"buyer", "seller"}
CONSTRAINT_KIND_ENUM = {"limit", "min", "max", "must", "must_not"}
CONSTRAINT_DIMENSION_ENUM = {"price", "time", "docs", "delivery", "warranty", "condition", "payment", "inspection", "other"}
TRUTH_STATUS_ENUM = {"claimed", "unverified", "verified", "contradicted"}
INTEREST_CATEGORY_ENUM = {"risk", "speed", "trust", "quality", "cost", "convenience", "status", "other"}
LEVERAGE_TYPE_ENUM = {"other_buyer", "scarcity", "authority", "walk_away", "alternatives", "time"}
EVIDENCE_TYPE_ENUM = {"doc", "photo", "invoice", "history", "link", "message", "other"}
AGREEMENT_STATE_ENUM = {"none", "tentative", "near", "agreed", "stalled"}

NEGOTIATION_STANCE_KEYS = {
    "flexibility",
    "firmness",
    "credibility",
    "time_pressure",
    "leverage_strength",
    "cooperation",
    "value_alignment",
    "deal_readiness",
    "risk_level",
}
NEGOTIATION_REASON_KEYS = {
    "price_position_signal",
    "constraint_signal",
    "interest_signal",
    "concession_signal",
    "time_pressure_signal",
    "leverage_signal",
    "credibility_signal",
    "value_tradeoff_signal",
    "deal_readiness_signal",
    "risk_signal",
}

BEHAVIOR_GUIDANCE_RECOMMENDED_MOVES = {"probe", "reframe", "deescalate", "close", "hold", "tradeoff"}
BEHAVIOR_GUIDANCE_EPISTEMIC_STYLE = {"hedged", "neutral", "direct"}

MAX_ITEMS = {
    "commitments": 8,
    "offers": 8,
    "constraints": 10,
    "interests": 8,
    "concessions": 8,
    "leverage_claims": 8,
    "evidence": 10,
    "open_points": 8,
    "missing_info": 8,
    "ambiguity_types": 8,
    "hypotheses": 8,
    "reasons": 10,
}
MAX_STR_LEN = {
    "text": 240,
    "short_text": 120,
    "evidence": 180,
    "item": 80,
    "key": 48,
}
MAX_META_DEPTH = 3
MAX_META_KEYS = 24
MAX_META_CHARS = 1200


def clamp01(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if out < 0.0:
        return 0.0
    if out > 1.0:
        return 1.0
    return out


def to_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def trim(value: Any, max_len: int) -> str:
    if value is None:
        return ""
    txt = str(value).strip()
    return txt[:max_len]


def enum_or(value: Any, allowed: set[str], default: str) -> str:
    txt = str(value).strip()
    if txt in allowed:
        return txt
    return default
