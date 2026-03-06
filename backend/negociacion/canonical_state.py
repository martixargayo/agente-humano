from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .shared_types import (
    ConversationAct,
    PlannerStatus,
    SafetyDomain,
    SafetyPolicyAction,
    SafetyRiskLevel,
    StyleTone,
    ThreadMode,
)

# ----------------------
# Threading OpenAI
# ----------------------


class SessionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thread_mode_override: ThreadMode | None


class OpenAIThreadState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: ThreadMode
    conversation_id: str | None
    previous_response_id: str | None




class DialogueMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str

# ----------------------
# Persona
# ----------------------


class PersonaPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role_identity: str
    negotiation_goal: str
    question_strategy: Literal["single_step", "minimal"]
    allow_topic_shift: bool


class PersonaExpressive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tone: StyleTone
    lexical_style: Literal["plain", "professional"]
    max_sentences_default: int


class PersonaState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: PersonaPolicy
    expressive: PersonaExpressive


# ----------------------
# Relación
# ----------------------


class RelationshipState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trust_level: Literal["low", "medium", "high"]
    rapport_level: Literal["low", "medium", "high"]
    last_interaction_note: str | None


# ----------------------
# Memoria
# ----------------------


class MemoryProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_name: str | None
    preferred_language: str
    risk_tolerance: Literal["low", "medium", "high"]


class MemoryEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: str
    event_summary: str
    turn_id: str


class MemoryWorking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_user_goal: str | None
    pending_question: str | None
    negotiation_stage: Literal["discovery", "proposal", "closing", "unknown"]


# ----------------------
# Plan, safety, voz
# ----------------------


class PlanState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_status: PlannerStatus
    current_act: ConversationAct
    current_goal: str


class SafetyState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_level: SafetyRiskLevel
    active_domain: SafetyDomain
    action: SafetyPolicyAction
    reason: str | None


class VoiceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_name: str
    speed: Literal["slow", "normal", "fast"]


# ----------------------
# Estado global canónico
# ----------------------


class CanonicalState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_settings: SessionSettings
    openai_thread: OpenAIThreadState
    recent_messages: List[DialogueMessage]
    persona: PersonaState
    relationship: RelationshipState
    memory_profile: MemoryProfile
    memory_episodic: List[MemoryEpisode]
    memory_working: MemoryWorking
    plan: PlanState
    safety: SafetyState
    voice: VoiceState
    trace: dict | None
