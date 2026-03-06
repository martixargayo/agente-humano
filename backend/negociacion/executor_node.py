from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .canonical_state import DialogueMessage, MemoryEpisode, MemoryProfile, MemoryWorking, PersonaExpressive
from .memory_node import TraceMeta, UserTurn
from .planner_node import PlannerOutput
from .shared_types import ConversationAct, ExecutorStatus, SafetyDomain, SafetyPolicyAction


class TaskContractExecutor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_realize_planner_output: bool
    cannot_change_conversation_act: bool


class MemoryForUse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile_snippet: MemoryProfile
    working_snippet: MemoryWorking
    episodic_snippet: List[MemoryEpisode]


class ExecutorSafetyLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: SafetyPolicyAction
    blocked_domains: List[SafetyDomain]
    overclaim_block: bool


class TTSHints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_name: str
    speaking_speed: Literal["slow", "normal", "fast"]


class ExecutorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_contract: TaskContractExecutor
    expressive_persona: PersonaExpressive
    planner_output: PlannerOutput
    recent_dialogue_short: List[DialogueMessage]
    user_turn: UserTurn
    memory_for_use: MemoryForUse
    safety_limits: ExecutorSafetyLimits
    tts_hints: TTSHints
    style_examples: List[str]
    trace_meta: TraceMeta


class ExecutorTTS(BaseModel):
    model_config = ConfigDict(extra="forbid")
    voice_name: str
    speaking_speed: Literal["slow", "normal", "fast"]


class ExecutorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str
    status: ExecutorStatus
    spoken_text: str
    conversation_act_realized: ConversationAct
    memory_used: List[str]
    tts: ExecutorTTS
    refusal_reason: str | None
