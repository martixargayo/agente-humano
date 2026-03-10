from __future__ import annotations

from typing import Any, List, Literal

from pydantic import BaseModel, ConfigDict

from ..state.canonical_state import MemoryWorkingState, NegotiationState, PersonaPolicy, PlannerState, SceneState
from .memory_node import DialogueMessage, TraceMeta, UserTurn
from ..state.shared_types import NegotiationPhase

PlannerDecision = Literal[
    "hold",
    "ask",
    "counter",
    "accept",
    "reject",
    "close",
]


class PlannerTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_name: Literal["planner"]
    objective: str
    completion_criteria: list[str]
    output_schema_version: Literal["planner.v3"]


class PhaseCard(BaseModel):
    model_config = ConfigDict(extra="allow")
    phase: NegotiationPhase
    guidance: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


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
    scene_state: SceneState
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
    memory_targets: list[str]
    done_criteria: list[str]
