from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .canonical_state import DialogueMessage, MemoryEpisode, MemoryProfile, MemoryWorking, RelationshipState
from .shared_types import SafetyDomain, SafetyPolicyAction, SafetyRiskLevel


class UserTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str
    normalized_text: str
    modality: Literal["text"]
    language: str
    timestamp_utc: str




class TaskContractPlanner(BaseModel):
    model_config = ConfigDict(extra="forbid")
    single_visible_persona: bool
    executor_cannot_replan: bool
    success_definition: str

class TraceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str
    timestamp_utc: str


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_contract: TaskContractPlanner
    relationship_state: RelationshipState
    memory_profile: MemoryProfile
    memory_working: MemoryWorking
    recent_dialogue: List[DialogueMessage]
    user_turn: UserTurn
    trace_meta: TraceMeta


class MemoryPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    profile_user_name: str | None
    profile_preferred_language: str | None
    profile_risk_tolerance: Literal["low", "medium", "high"] | None
    episodic_append: List[MemoryEpisode]
    working_current_user_goal: str | None
    working_pending_question: str | None
    working_negotiation_stage: Literal["discovery", "proposal", "closing", "unknown"] | None
    relationship_trust_level: Literal["low", "medium", "high"] | None
    relationship_rapport_level: Literal["low", "medium", "high"] | None
    relationship_last_interaction_note: str | None
    safety_risk_level: SafetyRiskLevel | None
    safety_active_domain: SafetyDomain | None
    safety_action: SafetyPolicyAction | None
    safety_reason: str | None
