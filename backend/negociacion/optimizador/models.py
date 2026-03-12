from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


OverrideCategory = Literal["prompt", "config", "contextual"]
OverrideScope = Literal["this_turn", "this_conversation", "this_optimizer_session"]


class SessionRef(BaseModel):
    user_id: str
    session_id: str


class OverrideEntry(BaseModel):
    category: OverrideCategory
    key: str
    value: Any
    scope: OverrideScope = "this_optimizer_session"
    conversation_id: str | None = None
    turn_id: str | None = None


class OverrideUpdateRequest(BaseModel):
    mode: Literal["mirror", "sandbox"] | None = None
    entries: list[OverrideEntry] = Field(default_factory=list)


class ConfirmOverridesRequest(BaseModel):
    entries: list[OverrideEntry] = Field(default_factory=list)


class SandboxTurnRequest(BaseModel):
    optimizer_session_id: str = "default"
    user_id: str
    session_id: str
    message: str
    conversation_id: str | None = None
    scope_turn_id: str | None = None
    repeat_from_turn_id: str | None = None


class SandboxCloneRequest(BaseModel):
    optimizer_session_id: str = "default"
    source_user_id: str
    source_session_id: str
    source_conversation_id: str | None = None


class NewConversationRequest(BaseModel):
    optimizer_session_id: str = "default"
    user_id: str
    session_id: str


class BootstrapSessionRequest(BaseModel):
    user_id: str = "u_optimizador"
    session_id: str = "optimizador-main"


class SaveCaseRequest(BaseModel):
    turn_id: str
    family: Literal["memory", "phase", "planner", "executor", "end_to_end", "guardrails"]
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class CompareTurnsRequest(BaseModel):
    turn_a: str
    turn_b: str


class OptimizerChatTurnRequest(BaseModel):
    message: str
    repeat_from_turn_id: str | None = None


class ActiveOptimizerChatBinding(BaseModel):
    optimizer_session_id: str
    user_id: str
    session_id: str
    conversation_id: str | None = None


class ActiveOptimizerChatHistoryResponse(BaseModel):
    binding: ActiveOptimizerChatBinding
    items: list[dict[str, Any]] = Field(default_factory=list)
