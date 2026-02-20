from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, confloat, conlist, field_validator

from ..config import get_negotiation_model_config
from ..schemas import ReasonKey
ALLOWED_NEGOTIATION_DOMAIN_KEYS = set()

NEGOTIATION_CONFIG = get_negotiation_model_config()
BELIEF_MODEL = NEGOTIATION_CONFIG.belief.model
BELIEF_TEMPERATURE = NEGOTIATION_CONFIG.belief.temperature

REASON_PRIORITY = {
    "price_signal": 0,
    "deadline_signal": 1,
    "other_buyer_signal": 2,
    "concession_signal": 3,
    "docs_signal": 4,
    "tone_signal": 5,
}


class BeliefReasonModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weight: confloat(ge=0.0, le=1.0) = 0.5
    confidence: confloat(ge=0.0, le=1.0) = 0.5
    evidence: str = ""


class BeliefStanceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    deal_feasibility: confloat(ge=0.0, le=1.0) = 0.5
    seller_flexibility: confloat(ge=0.0, le=1.0) = 0.5


class BeliefDynamicsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interaction_health: Literal["stable", "tense", "stalled"] = "stable"
    last_update_evidence: str = ""


class BeliefToMModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seller_goals: conlist(str, max_length=6) = Field(default_factory=list)
    seller_tactics: conlist(str, max_length=6) = Field(default_factory=list)
    seller_belief_about_me: conlist(str, max_length=6) = Field(default_factory=list)
    confidence: confloat(ge=0.0, le=1.0) = 0.4


class BeliefStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stance: BeliefStanceModel
    reasons: dict[ReasonKey, BeliefReasonModel] = Field(default_factory=dict)
    hypotheses: conlist(str, max_length=5) = Field(default_factory=list)
    hypotheses_structural: conlist(str, max_length=5) = Field(default_factory=list)
    hypotheses_observational: conlist(str, max_length=5) = Field(default_factory=list)
    evaluations: dict[str, confloat(ge=0.0, le=1.0)] = Field(default_factory=dict)
    dynamics: BeliefDynamicsModel
    tom: BeliefToMModel

    @field_validator("reasons")
    @classmethod
    def limit_reasons(
        cls, value: dict[ReasonKey, BeliefReasonModel]
    ) -> dict[ReasonKey, BeliefReasonModel]:
        if not isinstance(value, dict):
            return {}
        items = sorted(
            value.items(),
            key=lambda kv: (
                -(kv[1].weight * kv[1].confidence),
                REASON_PRIORITY.get(str(kv[0]), 999),
                str(kv[0]),
            ),
        )
        return dict(items[:6])


CRITICAL_FLAGS = tuple(list(ALLOWED_NEGOTIATION_DOMAIN_KEYS) + ["message_is_vague"])
