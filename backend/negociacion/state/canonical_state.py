from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator

from .shared_types import NegotiationPhase, ThreadMode
from ..contexts import resolve_default_negotiation_context, resolve_negotiation_context


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

EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS: dict[str, object] = {
    "schema_version": "negotiation_brief.v1",
    "contexto_de_mercado": {
        "valor_estimado": "El valor de mercado estimado de este modelo está en torno a 6000-6500 euros.",
        "lectura": "Ese rango refleja el valor base de mercado del coche, no el coste real de recurrir a la mejor alternativa disponible para Carlos.",
    },
    "realidad_de_la_alternativa": {
        "resumen": "Carlos no tiene una alternativa equivalente cómoda en la zona.",
        "detalle": "Comprar una unidad parecida fuera implica sumar transporte y matriculación.",
        "coste_equivalente_aproximado": "La mejor alternativa real se acerca a 8000 euros de coste total.",
        "lectura": "Por eso Carlos intentará acercarse al precio de mercado, pero sabe que debe ser realista si quiere este coche concreto.",
    },
    "objetivo_y_marco_de_decision": {
        "objetivo": "Intentar comprar por precio de mercado o lo más cerca posible.",
        "realismo": "Carlos sabe que le interesa este coche y que su alternativa real es más cara que el mercado base.",
        "criterio": "Empujará para mejorar el precio, pero un acuerdo por debajo de 8000 puede seguir pareciéndole bueno si el conjunto del trato encaja.",
        "por_encima_de_eso": "Por encima de ese nivel solo le compensa si el vendedor añade valor real suficiente o reduce riesgo de forma clara.",
    },
    "mapa_de_valor": {
        "nota": "Los valores aproximados sirven también como referencia para estimar el valor de otras concesiones parecidas que aparezcan en la negociación.",
        "items": [
            {
                "elemento": "1 año de garantía",
                "valor_aproximado_eur": 600,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Reduce riesgo postcompra y puede justificar pagar más.",
            },
            {
                "elemento": "ITV pasada antes de venderlo",
                "valor_aproximado_eur": None,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Reduce coste y fricción inmediata y puede justificar algo más de precio.",
            },
            {
                "elemento": "pack o kit de ruedas",
                "valor_aproximado_eur": None,
                "tipo_de_efecto": "suma_valor_real",
                "lectura": "Añade valor material directo y puede compensar parte del precio.",
            },
            {
                "elemento": "cerrar hoy mismo",
                "valor_aproximado_eur": 0,
                "tipo_de_efecto": "facilita_acuerdo",
                "lectura": "No justifica pagar más por sí solo, pero puede hacer a Carlos algo más flexible para cerrar.",
            },
            {
                "elemento": "operativa sencilla y poco roce",
                "valor_aproximado_eur": 0,
                "tipo_de_efecto": "facilita_acuerdo",
                "lectura": "No suma valor económico real al coche, pero ayuda a rebajar resistencia para llegar a un entendimiento.",
            },
        ],
    },
    "monedas_de_intercambio_del_comprador": {
        "puede_ofrecer": [
            {
                "elemento": "pago en efectivo",
                "uso": "Puede usarse para intentar que el vendedor baje expectativas o cierre antes.",
            },
            {
                "elemento": "encargarse del papeleo",
                "uso": "Puede usarse como contrapartida operativa para pedir mejor precio o mejores condiciones.",
            },
            {
                "elemento": "rapidez y facilidad para cerrar",
                "uso": "Puede usarse para reducir fricción del vendedor, pero no debe regalarse sin retorno.",
            },
        ]
    },
    "informacion_privada_sensible": {
        "no_conviene_revelar_espontaneamente": [
            "El coste real de su alternativa.",
            "La escasez de alternativas equivalentes en la zona.",
            "Su flexibilidad real.",
            "Qué concesiones valora más internamente.",
        ],
        "lectura": "Si el vendedor no lo sabe y lo intenta descubrir, conviene evitar revelarlo. Si el vendedor ya lo sabe de forma explícita y lo dice correctamente, no tiene sentido negarlo de manera artificial.",
    },
}


def _load_persona_defaults(context_id: str | None = None) -> dict[str, dict[str, object]]:
    path = resolve_negotiation_context(context_id).persona_path if context_id else resolve_default_negotiation_context().persona_path
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


def _load_negotiation_brief_defaults(context_id: str | None = None) -> dict[str, object]:
    path = resolve_negotiation_context(context_id).negotiation_brief_path if context_id else resolve_default_negotiation_context().negotiation_brief_path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS
    if not isinstance(raw, dict):
        return EMERGENCY_NEGOTIATION_BRIEF_DEFAULTS
    return raw


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


class NegotiationBriefMarketContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor_estimado: str
    lectura: str


class NegotiationBriefAlternativeReality(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumen: str
    detalle: str
    coste_equivalente_aproximado: str
    lectura: str


class NegotiationBriefObjectiveFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objetivo: str
    realismo: str
    criterio: str
    por_encima_de_eso: str


class NegotiationBriefValueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elemento: str
    valor_aproximado_eur: float | None
    tipo_de_efecto: str
    lectura: str


class NegotiationBriefValueMap(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nota: str
    items: list[NegotiationBriefValueItem]


class NegotiationBriefBuyerTradeoffItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    elemento: str
    uso: str


class NegotiationBriefBuyerTradeoffs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puede_ofrecer: list[NegotiationBriefBuyerTradeoffItem]


class NegotiationBriefSensitiveInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    no_conviene_revelar_espontaneamente: list[str]
    lectura: str


class NegotiationBriefState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["negotiation_brief.v1"]
    contexto_de_mercado: NegotiationBriefMarketContext
    realidad_de_la_alternativa: NegotiationBriefAlternativeReality
    objetivo_y_marco_de_decision: NegotiationBriefObjectiveFrame
    mapa_de_valor: NegotiationBriefValueMap
    monedas_de_intercambio_del_comprador: NegotiationBriefBuyerTradeoffs
    informacion_privada_sensible: NegotiationBriefSensitiveInfo


def _default_negotiation_brief_state() -> NegotiationBriefState:
    return NegotiationBriefState.model_validate(_load_negotiation_brief_defaults())


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


class NegotiationOffer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    extras: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    is_currently_active: bool = True
    source_turn_role: Literal["user", "assistant"] | None = None


class TentativeAgreement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str | None = None
    price_amount: float | None = None
    currency: str | None = None
    extras: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)


class NegotiationStallState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_hard_stalemate: bool = False
    stalemate_reason: str | None = None
    self_ultimatum_active: bool = False
    self_ultimatum_summary: str | None = None


class NegotiationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str = "inactive"
    active_axes: list[str] = Field(default_factory=list)
    last_offer_self: NegotiationOffer | None = None
    last_offer_other: NegotiationOffer | None = None
    tentative_agreement: TentativeAgreement | None = None
    stall_state: NegotiationStallState = Field(default_factory=NegotiationStallState)
    blockers: list[str] = Field(default_factory=list)
    next_open_loop: str | None = None

    @field_validator("last_offer_self", "last_offer_other", mode="before")
    @classmethod
    def _coerce_legacy_offer(cls, value: object) -> object:
        if isinstance(value, str):
            return {
                "summary": value,
                "price_amount": None,
                "currency": None,
                "extras": [],
                "conditions": [],
                "is_currently_active": True,
                "source_turn_role": None,
            }
        return value


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
    copresent: bool = True
    encounter_in_progress: bool = True
    conversation_only: bool = True


class TraceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str | None
    last_node_statuses: dict[str, str] = Field(default_factory=dict)
    last_fallbacks: list[str] = Field(default_factory=list)
    last_refusals: list[str] = Field(default_factory=list)


class NegotiationUiState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    finish_button_armed: bool = False


class CanonicalState(BaseModel):
    """Fuente mínima de verdad del dominio de negociación."""

    model_config = ConfigDict(extra="forbid")

    session: SessionMeta
    openai_thread: OpenAIThreadState
    persona: PersonaState
    negotiation_brief: NegotiationBriefState = Field(default_factory=_default_negotiation_brief_state)
    memory_episodic: list[MemoryEpisodicItem]
    memory_working: MemoryWorkingState
    negotiation_state: NegotiationState
    planner_state: PlannerState
    scene_state: SceneState
    ui_state: NegotiationUiState = Field(default_factory=NegotiationUiState)
    trace: TraceState


def build_default_canonical_state(
    *,
    session_id: str,
    thread_mode: ThreadMode,
    user_id: str | None = None,
    avatar_id: str | None = None,
    now_iso: str | None = None,
    context_id: str | None = None,
) -> CanonicalState:
    timestamp = now_iso or datetime.now(timezone.utc).isoformat()
    persona_defaults = _load_persona_defaults(context_id=context_id)
    negotiation_brief_defaults = _load_negotiation_brief_defaults(context_id=context_id)
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
        negotiation_brief=NegotiationBriefState.model_validate(negotiation_brief_defaults),
        memory_episodic=[],
        memory_working=MemoryWorkingState(current_topic=None, pending_question=None, last_turn_summary=None),
        negotiation_state=NegotiationState(
            status="inactive",
            active_axes=[],
            last_offer_self=None,
            last_offer_other=None,
            tentative_agreement=None,
            stall_state=NegotiationStallState(
                is_hard_stalemate=False,
                stalemate_reason=None,
                self_ultimatum_active=False,
                self_ultimatum_summary=None,
            ),
            blockers=[],
            next_open_loop=None,
        ),
        planner_state=PlannerState(
            current_phase=None,
            previous_phase=None,
            current_turn_goal=None,
            topics_touched_current_phase=[],
            topics_touched_previous_phases=[],
            recent_phase_history=[],
        ),
        scene_state=SceneState(
            copresent=True,
            encounter_in_progress=True,
            conversation_only=True,
        ),
        ui_state=NegotiationUiState(finish_button_armed=False),
        trace=TraceState(turn_id=None, last_node_statuses={}, last_fallbacks=[], last_refusals=[]),
    )
