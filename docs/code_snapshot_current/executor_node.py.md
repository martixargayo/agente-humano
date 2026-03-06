# File Snapshot

Original path:
`backend/negociacion/executor_node.py`

Snapshot status:
`current`

Language / type:
`python`

```python
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .canonical_state import PersonaExpressive
from .memory_node import DialogueMessage, TraceMeta, UserTurn
from .planner_node import PhaseCard, PlannerOutput, SelectedMemoryItem
from .shared_types import NegotiationPhase


class ExecutorTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_name: Literal["executor"]
    objective: str
    success_definition: str


class ExecutorResponseLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_sentences: int
    max_questions: int
    allow_topic_shift: bool
    allow_personal_disclosure: bool


class ExecutorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["executor_input.v1"]
    task_contract: ExecutorTaskContract
    persona_expressive: PersonaExpressive
    current_phase: NegotiationPhase
    phase_card: PhaseCard
    user_turn: UserTurn
    recent_dialogue_short: List[DialogueMessage]
    planner_output: PlannerOutput
    selected_memory_for_reference: List[SelectedMemoryItem]
    response_limits: ExecutorResponseLimits
    trace_meta: TraceMeta


class ExecutorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["executor.v1"]
    status: Literal["deliver", "clarify", "refuse"]
    spoken_text: str
    memory_used: list[str]
    refusal_reason: str | None

```
