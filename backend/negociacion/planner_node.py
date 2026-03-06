from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .canonical_state import DialogueMessage, MemoryEpisode, MemoryProfile, MemoryWorking, PersonaPolicy, RelationshipState, SafetyState
from .memory_node import TaskContractPlanner, TraceMeta, UserTurn
from .shared_types import (
    ConversationAct,
    DirectnessLevel,
    EmotionalIntensity,
    InitiativeLevel,
    LengthBand,
    PlannerStatus,
    SafetyDomain,
    SafetyPolicyAction,
    SafetyRiskLevel,
    StyleTone,
)


class SelectedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: MemoryProfile
    working: MemoryWorking
    episodic_recent: List[MemoryEpisode]


class ExternalEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str
    summary: str
    confidence: Literal["low", "medium", "high"]


class PlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_contract: TaskContractPlanner
    persona_policy: PersonaPolicy
    relationship_state: RelationshipState
    working_state: MemoryWorking
    recent_dialogue: List[DialogueMessage]
    selected_memory: SelectedMemory
    external_evidence: List[ExternalEvidenceItem]
    user_turn: UserTurn
    safety_flags: SafetyState
    trace_meta: TraceMeta


class PlannerSituation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_intent: str
    user_emotion: Literal["neutral", "frustrated", "positive", "unknown"]


class PlannerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_act: ConversationAct
    turn_goal: str
    ask_clarification: bool


class PlannerContentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_points: List[str]
    forbidden_topics: List[str]


class PlannerStyleBand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tone: StyleTone
    length_band: LengthBand
    directness: DirectnessLevel
    initiative: InitiativeLevel
    emotional_intensity: EmotionalIntensity


class PlannerLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_sentences: int
    max_questions: int
    allow_topic_shift: bool
    allow_advice: bool
    allow_personal_disclosure: bool


class PlannerSafety(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_level: SafetyRiskLevel
    policy_action: SafetyPolicyAction
    refusal_reason: str | None
    blocked_domains: List[SafetyDomain]


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    status: PlannerStatus
    situation: PlannerSituation
    policy: PlannerPolicy
    content_plan: PlannerContentPlan
    style_band: PlannerStyleBand
    limits: PlannerLimits
    safety: PlannerSafety
    done_criteria: List[str]
