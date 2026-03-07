from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .shared_types import NegotiationPhase, StyleTone, ThreadMode


def _load_persona_defaults() -> dict[str, dict[str, object]]:
    path = Path(__file__).resolve().parent.parent / "prompts" / "persona.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("persona.json debe ser un objeto JSON")
    policy = raw.get("policy")
    expressive = raw.get("expressive")
    if not isinstance(policy, dict) or not isinstance(expressive, dict):
        raise ValueError("persona.json debe contener 'policy' y 'expressive' como objetos")
    return {"policy": policy, "expressive": expressive}


class SessionMeta(BaseModel):
    """Metadatos persistentes de sesión."""

    model_config = ConfigDict(extra="forbid")
    session_id: str
    user_id: str | None
    avatar_id: str | None
    created_at: str
    updated_at: str

    # /// Este grupo se inicializa por código al crear sesión.
    # /// `updated_at` debe refrescarse al persistir estado.


class OpenAIThreadState(BaseModel):
    """Threading OpenAI (no estado de dominio)."""

    model_config = ConfigDict(extra="forbid")
    thread_mode: ThreadMode
    conversation_id: str | None
    previous_response_id: str | None


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


class MemoryWorkingState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_topic: str | None
    pending_question: str | None
    last_turn_summary: str | None
    # /// Arranca en `None` al crear sesión; tras el primer turno memory node lo refresca con string factual.


class NegotiationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    last_offer_self: str | None
    last_offer_other: str | None
    blockers: list[str] = Field(default_factory=list)


class PlannerState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_phase: NegotiationPhase | None
    previous_phase: NegotiationPhase | None
    current_turn_goal: str | None
    topics_touched_current_phase: list[str] = Field(default_factory=list)
    topics_touched_previous_phases: list[str] = Field(default_factory=list)


class TraceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str | None
    last_node_statuses: dict[str, str] = Field(default_factory=dict)
    last_fallbacks: list[str] = Field(default_factory=list)
    last_refusals: list[str] = Field(default_factory=list)


class CanonicalState(BaseModel):
    """Fuente mínima de verdad del dominio de negociación."""

    model_config = ConfigDict(extra="forbid")

    session: SessionMeta
    openai_thread: OpenAIThreadState
    persona: PersonaState
    memory_episodic: list[MemoryEpisodicItem]
    memory_working: MemoryWorkingState
    negotiation_state: NegotiationState
    planner_state: PlannerState
    trace: TraceState


def build_default_canonical_state(
    *,
    session_id: str,
    thread_mode: ThreadMode,
    user_id: str | None = None,
    avatar_id: str | None = None,
    now_iso: str | None = None,
) -> CanonicalState:
    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    return CanonicalState(
        session=SessionMeta(
            session_id=session_id,
            user_id=user_id,
            avatar_id=avatar_id,
            created_at=timestamp,
            updated_at=timestamp,
        ),
        openai_thread=OpenAIThreadState(thread_mode=thread_mode, conversation_id=None, previous_response_id=None),
        persona=PersonaState(
            policy=PersonaPolicy.model_validate(_load_persona_defaults()["policy"]),
            expressive=PersonaExpressive.model_validate(_load_persona_defaults()["expressive"]),
        ),
        memory_episodic=[],
        memory_working=MemoryWorkingState(current_topic=None, pending_question=None, last_turn_summary=None),
        negotiation_state=NegotiationState(last_offer_self=None, last_offer_other=None, blockers=[]),
        planner_state=PlannerState(
            current_phase=None,
            previous_phase=None,
            current_turn_goal=None,
            topics_touched_current_phase=[],
            topics_touched_previous_phases=[],
        ),
        trace=TraceState(turn_id=None, last_node_statuses={}, last_fallbacks=[], last_refusals=[]),
    )
