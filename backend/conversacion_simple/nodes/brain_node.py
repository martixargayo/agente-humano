from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .common import DialogueMessage, TraceMeta, UserTurn
from ..state.canonical_state import (
    ConversationSimpleBriefState,
    ConversationSimpleConversationState,
    ConversationSimpleMemoryWorkingState,
    ConversationSimplePhaseCardsState,
    ConversationSimplePersonaState,
)


class BrainTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_name: Literal["brain"]
    objective: str
    completion_criteria: list[str]
    output_schema_version: Literal["brain.v1"]


class BrainStatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_state: ConversationSimpleConversationState
    memory_working: ConversationSimpleMemoryWorkingState
    memory_episodic_append: list[dict[str, str]] = Field(default_factory=list)


class BrainAssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class BrainObservability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rationale_summary: str | None = None


class BrainInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["brain_input.v1"]
    task_contract: BrainTaskContract
    persona: ConversationSimplePersonaState
    conversation_brief: ConversationSimpleBriefState
    phase_cards: ConversationSimplePhaseCardsState
    conversation_state: ConversationSimpleConversationState
    memory_working: ConversationSimpleMemoryWorkingState
    memory_compacted_summary: str
    recent_dialogue_short: list[DialogueMessage]
    user_turn: UserTurn
    trace_meta: TraceMeta


class BrainOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["brain.v1"]
    status: Literal["deliver", "clarify", "refuse"]
    assistant_response: BrainAssistantResponse
    state_patch: BrainStatePatch
    observability: BrainObservability = Field(default_factory=BrainObservability)
