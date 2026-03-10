from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .shared_types import NegotiationPhase, ThreadMode


EMERGENCY_PERSONA_DEFAULTS: dict[str, dict[str, object]] = {
    "policy": {
        "identidad_operativa": "Eres Carlos, comprador prudente y orientado a viabilidad del acuerdo.",
        "objetivo_privado": "Mantener continuidad operativa de la negociación con foco en riesgo, condiciones y coste total.",
        "criterio_de_decision": "Avanza solo con claridad suficiente; evita cierres por presión o ambigüedad.",
        "disciplina_negociadora": "Toda concesión requiere contrapartida verificable y proporcional.",
        "limites_privados": "No revelar techo real, urgencia ni alternativas privadas.",
        "principios_de_avance": "Cada turno debe generar al menos un avance útil en claridad, condiciones, compromiso o cierre.",
    },
    "expressive": {
        "identidad_en_escena": "Hablas como Carlos, comprador humano y creíble en conversación real.",
        "marco_conversacional": "Interés genuino por el coche con prudencia y criterio propio.",
        "voz_y_estilo": "Español natural, claro y conversacional; firmeza serena.",
        "naturalidad": "Responder primero al turno actual y evitar fórmulas robóticas.",
        "huella_conversacional": "Buen juicio, paciencia y cautela sana durante toda la negociación.",
    },
}


def _load_persona_defaults() -> dict[str, dict[str, object]]:
    path = Path(__file__).resolve().parent.parent / "prompts" / "persona.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return EMERGENCY_PERSONA_DEFAULTS
    if not isinstance(raw, dict):
        return EMERGENCY_PERSONA_DEFAULTS
    policy = raw.get("policy")
    expressive = raw.get("expressive")
    if not isinstance(policy, dict) or not isinstance(expressive, dict):
        return EMERGENCY_PERSONA_DEFAULTS
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
    identidad_operativa: str
    objetivo_privado: str
    criterio_de_decision: str
    disciplina_negociadora: str
    limites_privados: str
    principios_de_avance: str


class PersonaExpressive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identidad_en_escena: str
    marco_conversacional: str
    voz_y_estilo: str
    naturalidad: str
    huella_conversacional: str


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
    recent_phase_history: list[NegotiationPhase] = Field(default_factory=list)


class SceneState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    copresent: bool = False
    encounter_in_progress: bool = False
    conversation_only: bool = True


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
    scene_state: SceneState
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
    persona_defaults = _load_persona_defaults()
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
            policy=PersonaPolicy.model_validate(persona_defaults["policy"]),
            expressive=PersonaExpressive.model_validate(persona_defaults["expressive"]),
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
            recent_phase_history=[],
        ),
        scene_state=SceneState(
            copresent=False,
            encounter_in_progress=False,
            conversation_only=True,
        ),
        trace=TraceState(turn_id=None, last_node_statuses={}, last_fallbacks=[], last_refusals=[]),
    )
