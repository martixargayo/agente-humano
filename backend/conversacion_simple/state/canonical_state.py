from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .shared_types import ConversationSimplePhase
from ..contexts import resolve_default_conversacion_simple_context, resolve_conversacion_simple_context
from negociacion.state.canonical_state import OpenAIThreadState, SessionMeta
from negociacion.state.shared_types import ThreadMode


class ConversationSimplePersonaState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: dict[str, str] = Field(default_factory=dict)
    expressive: dict[str, str] = Field(default_factory=dict)


class ConversationSimpleBriefState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "conversation_brief.v1"
    objective: str = ""
    constraints: list[str] = Field(default_factory=list)


class ConversationSimpleMemoryEpisodicItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal["important_fact", "intent", "constraint", "commitment"]
    event_summary: str
    turn_id: str


class ConversationSimpleMemoryWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_topic: str | None = None
    pending_question: str | None = None
    last_turn_summary: str | None = None


class ConversationSimpleConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: ConversationSimplePhase | None = None
    status: str = "active"
    current_turn_goal: str | None = None


class ConversationSimpleUiState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finish_button_armed: bool = False


class ConversationSimpleTraceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: str | None = None
    last_status: str | None = None


class ConversationSimpleMemoryMaintenanceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pending: bool = False
    attempts: int = 0
    retry_limit: int = 3
    last_status: str | None = None
    last_reason: str | None = None
    last_mode: str | None = None
    last_compacted_turn_id: str | None = None


class ConversationSimpleCanonicalState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: SessionMeta
    openai_thread: OpenAIThreadState
    persona: ConversationSimplePersonaState
    conversation_brief: ConversationSimpleBriefState
    memory_episodic: list[ConversationSimpleMemoryEpisodicItem] = Field(default_factory=list)
    memory_compacted_summary: str = ""
    memory_maintenance: ConversationSimpleMemoryMaintenanceState = Field(default_factory=ConversationSimpleMemoryMaintenanceState)
    memory_working: ConversationSimpleMemoryWorkingState = Field(default_factory=ConversationSimpleMemoryWorkingState)
    conversation_state: ConversationSimpleConversationState = Field(default_factory=ConversationSimpleConversationState)
    ui_state: ConversationSimpleUiState = Field(default_factory=ConversationSimpleUiState)
    trace: ConversationSimpleTraceState = Field(default_factory=ConversationSimpleTraceState)


def _load_persona_defaults(context_id: str | None = None) -> dict[str, object]:
    path = (
        resolve_conversacion_simple_context(context_id).persona_path
        if context_id
        else resolve_default_conversacion_simple_context().persona_path
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return raw if isinstance(raw, dict) else {}


def parse_conversation_simple_brief_payload(payload: dict[str, object]) -> ConversationSimpleBriefState:
    objective = payload.get("objective")
    constraints = payload.get("constraints")
    return ConversationSimpleBriefState(
        schema_version=str(payload.get("schema_version") or "conversation_brief.v1"),
        objective=objective if isinstance(objective, str) else "",
        constraints=[item for item in constraints if isinstance(item, str)] if isinstance(constraints, list) else [],
    )


def _load_conversation_brief_defaults(context_id: str | None = None) -> ConversationSimpleBriefState:
    path = (
        resolve_conversacion_simple_context(context_id).conversation_brief_path
        if context_id
        else resolve_default_conversacion_simple_context().conversation_brief_path
    )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return parse_conversation_simple_brief_payload(raw if isinstance(raw, dict) else {})


def build_default_conversation_simple_canonical_state(
    *,
    session_id: str,
    thread_mode: ThreadMode,
    user_id: str | None = None,
    avatar_id: str | None = None,
    now_iso: str | None = None,
    context_id: str | None = None,
) -> ConversationSimpleCanonicalState:
    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    persona_raw = _load_persona_defaults(context_id=context_id)
    policy = persona_raw.get("policy") if isinstance(persona_raw.get("policy"), dict) else {}
    expressive = persona_raw.get("expressive") if isinstance(persona_raw.get("expressive"), dict) else {}
    return ConversationSimpleCanonicalState(
        session=SessionMeta(
            session_id=session_id,
            user_id=user_id,
            avatar_id=avatar_id,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        openai_thread=OpenAIThreadState(thread_mode=thread_mode, conversation_id=None, previous_response_id=None),
        persona=ConversationSimplePersonaState(
            policy={k: v for k, v in policy.items() if isinstance(k, str) and isinstance(v, str)},
            expressive={k: v for k, v in expressive.items() if isinstance(k, str) and isinstance(v, str)},
        ),
        conversation_brief=_load_conversation_brief_defaults(context_id=context_id),
        memory_episodic=[],
        memory_compacted_summary="",
        memory_maintenance=ConversationSimpleMemoryMaintenanceState(),
        memory_working=ConversationSimpleMemoryWorkingState(),
        conversation_state=ConversationSimpleConversationState(),
        ui_state=ConversationSimpleUiState(finish_button_armed=False),
        trace=ConversationSimpleTraceState(turn_id=None, last_status=None),
    )
