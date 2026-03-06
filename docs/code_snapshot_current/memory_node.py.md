# File Snapshot

Original path:
`backend/negociacion/memory_node.py`

Snapshot status:
`current`

Language / type:
`python`

```python
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from .canonical_state import MemoryEpisodicItem, MemoryWorkingState


class DialogueMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: str


class UserTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_text: str
    normalized_text: str
    modality: Literal["text", "stt"]
    language: str
    timestamp_iso: str


class TraceMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str
    prompt_version: str
    schema_version: str
    model_target: str


class MemoryTaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_name: Literal["memory"]
    objective: str
    success_definition: str


class MemoryEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal[
        "offer",
        "commitment",
        "blocker",
        "avoidance",
        "important_fact",
        "topic_closure",
    ]
    summary: str
    turn_id: str


class MemoryWorking(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_topic: str | None
    pending_question: str | None
    last_turn_summary: str


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["memory_input.v1"]
    task_contract: MemoryTaskContract
    user_turn: UserTurn
    recent_dialogue_short: List[DialogueMessage]
    memory_working_current: MemoryWorkingState
    recent_memory_episodic_short: List[MemoryEpisodicItem]
    trace_meta: TraceMeta


class MemoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["memory.v1"]
    episodic_append: list[MemoryEpisode]
    working_memory_new: MemoryWorking

```
