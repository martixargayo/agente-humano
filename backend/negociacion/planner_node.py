from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field

from .canonical_state import MemoryWorkingState, NegotiationState, PersonaPolicy, PlannerState
from .memory_node import DialogueMessage, TraceMeta, UserTurn
from .shared_types import NegotiationPhase

PlannerDecision = Literal[
    "none",
    "hold",
    "clarify",
    "counter",
    "accept",
    "reject",
    "close",
]


class PlannerTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_name: Literal["planner"]
    objective: str
    success_definition: str


class PhaseCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: NegotiationPhase
    guidance: str


class SelectedMemoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_id: str
    memory_summary: str


class PlannerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["planner_input.v1"]
    task_contract: PlannerTaskContract
    persona_policy: PersonaPolicy
    current_phase: NegotiationPhase
    phase_card: PhaseCard
    user_turn: UserTurn
    recent_dialogue_short: List[DialogueMessage]
    memory_working: MemoryWorkingState
    negotiation_state: NegotiationState
    planner_state: PlannerState
    selected_memory: List[SelectedMemoryItem]
    trace_meta: TraceMeta


class PlannerContentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    must_include: list[str]
    must_avoid: list[str]


class PlannerLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_sentences: int
    max_questions: int
    allow_topic_shift: bool
    allow_personal_disclosure: bool


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["planner.v3"]
    status: Literal["plan", "clarify", "refuse"]
    turn_goal: str
    decision: PlannerDecision
    content_plan: PlannerContentPlan
    limits: PlannerLimits
    memory_targets: list[str] = Field(default_factory=list)
    done_criteria: list[str]
