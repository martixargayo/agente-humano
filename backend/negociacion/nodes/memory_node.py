from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict

from ..state.canonical_state import MemoryEpisodicItem as CanonicalMemoryEpisodicItem, MemoryWorkingState, SceneState


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
    completion_criteria: list[str]
    output_schema_version: Literal["memory.v1"]


class MemoryEpisodicItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal[
        "offer",
        "commitment",
        "blocker",
        "avoidance",
        "important_fact",
        "topic_closure",
    ]
    event_summary: str
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
    scene_state: SceneState
    recent_memory_episodic_short: List[CanonicalMemoryEpisodicItem]
    trace_meta: TraceMeta


class MemoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["memory.v1"]
    episodic_append: list[MemoryEpisodicItem]
    working_memory_new: MemoryWorking
