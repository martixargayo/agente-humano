from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import List, Sequence, Tuple, TypedDict

import openai
from pydantic import BaseModel, ConfigDict, ValidationError

from state import SessionState, add_message, save_session_state

from .canonical_state import (
    CanonicalState,
    MemoryEpisodicItem,
    OpenAIThreadState,
    build_default_canonical_state,
)
from .executor_node import (
    ExecutorInput,
    ExecutorOutput,
    ExecutorResponseLimits,
    ExecutorTaskContract,
)
from .memory_node import DialogueMessage as MemoryDialogueMessage, MemoryEpisode, MemoryInput, MemoryOutput, MemoryTaskContract, MemoryWorking as MemoryWorkingOutput, TraceMeta, UserTurn
from .phase_classifier_node import (
    PhaseClassifierInput,
    PhaseClassifierOutput,
    build_phase_classifier_input,
    build_phase_classifier_messages,
)
from .planner_node import (
    PhaseCard,
    PlannerContentPlan,
    PlannerInput,
    PlannerLimits,
    PlannerOutput,
    PlannerTaskContract,
    SelectedMemoryItem,
)
from .shared_types import (
    NodeName,
    NegotiationPhase,
    SDKCompatibilityStatus,
    SafetyDomain,
    StructuredCallSource,
    ThreadMode,
)

logger = logging.getLogger(__name__)

OPENAI_MIN_VERSION = "1.40.0"
PHASE_CLASSIFIER_INPUT_SCHEMA_VERSION = "phase_classifier_input.v1"


class InputSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_turn_chars: int
    recent_dialogue_items: int


class ErrorSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


class NodeTraceLog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node: NodeName
    model: str
    prompt_version: str
    schema_version: str
    latency_ms: int
    retries: int
    input_summary: InputSummary
    output_status: str
    call_source: StructuredCallSource
    refusal: str | None
    parse_error: str | None
    error: ErrorSummary | None


class EvalGrades(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planner_coherence: str
    executor_naturalness: str
    planner_executor_agreement: bool
    safety_compliance: bool


class SDKCompatibilityInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    installed_version: str | None
    minimum_version: str
    status: SDKCompatibilityStatus
    details: str


class TurnTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turn_id: str
    timestamp_utc: str
    model_memory: str
    model_phase_classifier: str
    model_planner: str
    model_executor: str
    prompt_version_memory: str
    prompt_version_phase_classifier: str
    prompt_version_planner: str
    prompt_version_executor: str
    schema_version_memory: str
    schema_version_phase_classifier: str
    schema_version_planner: str
    schema_version_executor: str
    sdk_compatibility: SDKCompatibilityInfo
    grades: EvalGrades
    logs: List[NodeTraceLog]


class StructuredCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parsed_json: dict | None
    refusal: str | None
    parse_error: str | None
    exception_error: str | None
    response: object | None
    source: StructuredCallSource


class SafetyPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hard_baseline_enabled: bool
    optional_layer_enabled: bool


class NegotiationTurnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_key: str = "negotiation_canonical"
    prompts_dir: str
    model_memory: str = "gpt-5-nano"
    model_phase_classifier: str = "gpt-5-nano"
    model_planner: str = "o4-mini"
    model_executor: str = "gpt-5-nano"
    reasoning_effort_planner: str = "medium"
    thread_mode_default: ThreadMode = ThreadMode.conversation
    planner_store: bool = True
    memory_store: bool = False
    executor_store: bool = False
    max_recent_messages: int = 12
    max_executor_recent_turns: int = 4
    feature_safety: bool = True
    feature_traces: bool = True
    feature_eval_hooks: bool = True
    prompt_version_memory: str = "memory_v3"
    prompt_version_phase_classifier: str = "phase_classifier_v1"
    prompt_version_planner: str = "planner_v3"
    prompt_version_executor: str = "executor_v3"
    enforce_sdk_compatibility: bool = False


class FlowDetails(TypedDict):
    flow_name: str
    memory_key: str
    model_memory: str
    model_phase_classifier: str
    model_planner: str
    model_executor: str
    reasoning_effort_planner: str
    thread_mode_default: ThreadMode
    planner_store: bool
    memory_store: bool
    executor_store: bool
    max_recent_messages: int
    max_executor_recent_turns: int
    feature_safety: bool
    feature_traces: bool
    feature_eval_hooks: bool
    enforce_sdk_compatibility: bool


BASE_DIR = Path(__file__).resolve().parent

NEGOTIATION_FLOW_DETAILS: FlowDetails = {
    "flow_name": "negociacion",
    "memory_key": "negotiation_canonical",
    "model_memory": "gpt-5-nano",
    "model_phase_classifier": "gpt-5-nano",
    "model_planner": "o4-mini",
    "model_executor": "gpt-5-nano",
    "reasoning_effort_planner": "medium",
    "thread_mode_default": ThreadMode.conversation,
    "planner_store": True,
    "memory_store": False,
    "executor_store": False,
    "max_recent_messages": 12,
    "max_executor_recent_turns": 4,
    "feature_safety": True,
    "feature_traces": True,
    "feature_eval_hooks": True,
    "enforce_sdk_compatibility": False,
}


@dataclass
class StateRepository:
    memory_key: str

    def load_state(self, session_state: SessionState, thread_mode: ThreadMode) -> CanonicalState:
        raw = session_state.world_state.get(self.memory_key, {}) if isinstance(session_state.world_state, dict) else {}
        if isinstance(raw, dict):
            try:
                return CanonicalState.model_validate(raw)
            except ValidationError as exc:
                logger.error(
                    "canonical_state_validation_error memory_key=%s errors=%s fallback=default_state",
                    self.memory_key,
                    exc.errors(),
                )
        else:
            logger.error("canonical_state_invalid_type memory_key=%s raw_type=%s fallback=default_state", self.memory_key, type(raw).__name__)
        return _default_canonical_state(session_state=session_state, thread_mode=thread_mode)

    def save_state(self, session_state: SessionState, canonical_state: CanonicalState) -> None:
        session_state.world_state[self.memory_key] = canonical_state.model_dump(mode="json")

    def load_recent_dialogue(self, session_state: SessionState) -> List[MemoryDialogueMessage]:
        raw = session_state.world_state.get(f"{self.memory_key}_recent_dialogue", []) if isinstance(session_state.world_state, dict) else []
        if not isinstance(raw, list):
            return []
        recent: List[MemoryDialogueMessage] = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    recent.append(MemoryDialogueMessage.model_validate(item))
                except Exception:
                    continue
        return recent

    def save_recent_dialogue(self, session_state: SessionState, recent_dialogue: Sequence[MemoryDialogueMessage]) -> None:
        session_state.world_state[f"{self.memory_key}_recent_dialogue"] = [item.model_dump(mode="json") for item in recent_dialogue]

    def append_trace(self, session_state: SessionState, turn_trace: TurnTrace) -> None:
        traces = session_state.world_state.setdefault(f"{self.memory_key}_traces", [])
        if not isinstance(traces, list):
            traces = []
            session_state.world_state[f"{self.memory_key}_traces"] = traces
        traces.append(turn_trace.model_dump(mode="json"))


def build_negotiation_pipeline_config() -> NegotiationTurnConfig:
    return NegotiationTurnConfig(
        memory_key=NEGOTIATION_FLOW_DETAILS["memory_key"],
        prompts_dir=str(BASE_DIR / "prompts"),
        model_memory=NEGOTIATION_FLOW_DETAILS["model_memory"],
        model_phase_classifier=NEGOTIATION_FLOW_DETAILS["model_phase_classifier"],
        model_planner=NEGOTIATION_FLOW_DETAILS["model_planner"],
        model_executor=NEGOTIATION_FLOW_DETAILS["model_executor"],
        reasoning_effort_planner=NEGOTIATION_FLOW_DETAILS["reasoning_effort_planner"],
        thread_mode_default=NEGOTIATION_FLOW_DETAILS["thread_mode_default"],
        planner_store=NEGOTIATION_FLOW_DETAILS["planner_store"],
        memory_store=NEGOTIATION_FLOW_DETAILS["memory_store"],
        executor_store=NEGOTIATION_FLOW_DETAILS["executor_store"],
        max_recent_messages=NEGOTIATION_FLOW_DETAILS["max_recent_messages"],
        max_executor_recent_turns=NEGOTIATION_FLOW_DETAILS["max_executor_recent_turns"],
        feature_safety=NEGOTIATION_FLOW_DETAILS["feature_safety"],
        feature_traces=NEGOTIATION_FLOW_DETAILS["feature_traces"],
        feature_eval_hooks=NEGOTIATION_FLOW_DETAILS["feature_eval_hooks"],
        enforce_sdk_compatibility=NEGOTIATION_FLOW_DETAILS["enforce_sdk_compatibility"],
    )


def _default_canonical_state(session_state: SessionState | None = None, thread_mode: ThreadMode = ThreadMode.conversation) -> CanonicalState:
    session_id = session_state.session_id if session_state and session_state.session_id else "pending_session"
    user_id = session_state.user_id if session_state and session_state.user_id else None
    return build_default_canonical_state(session_id=session_id, user_id=user_id, thread_mode=thread_mode)


# ==================================================
# A) Construcción de contexto
# ==================================================

def _build_user_turn(user_message: str, now_iso: str) -> UserTurn:
    normalized = " ".join(user_message.strip().split())
    return UserTurn(raw_text=user_message, normalized_text=normalized, modality="text", language="es", timestamp_iso=now_iso)


def _compact_recent(recent: Sequence[MemoryDialogueMessage], max_messages: int) -> List[MemoryDialogueMessage]:
    return list(recent[-max_messages:])


PHASE_CARDS: dict[NegotiationPhase, str] = {
    NegotiationPhase.clima_humano: "Prioriza vínculo humano breve y transición natural hacia señales de negociación.",
    NegotiationPhase.descubrimiento_y_comprension: "Aclara variables, restricciones y contexto antes de empujar una propuesta.",
    NegotiationPhase.propuesta_creativa: "Estructura una propuesta concreta con opciones razonables y lenguaje claro.",
    NegotiationPhase.concesiones_y_ajuste_final: "Gestiona concesiones/contraofertas para acercar posiciones y reducir fricción.",
    NegotiationPhase.formalizacion_del_acuerdo: "Confirma términos finales y siguiente paso operativo para cerrar acuerdo.",
}


def _recent_phase_history(canonical_state: CanonicalState) -> List[NegotiationPhase]:
    items: List[NegotiationPhase] = []
    if canonical_state.planner_state.previous_phase is not None:
        items.append(canonical_state.planner_state.previous_phase)
    if canonical_state.planner_state.current_phase is not None:
        items.append(canonical_state.planner_state.current_phase)
    return items[-4:]


def _select_phase_card(current_phase: NegotiationPhase) -> PhaseCard:
    return PhaseCard(phase=current_phase, guidance=PHASE_CARDS[current_phase])


def build_phase_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta) -> PhaseClassifierInput:
    return build_phase_classifier_input(
        previous_phase=canonical_state.planner_state.previous_phase,
        recent_phase_history=_recent_phase_history(canonical_state),
        recent_turns=_compact_recent(recent_dialogue, 4),
        current_user_turn=user_turn,
        trace_meta=trace_meta,
    )


def _select_memory(canonical_state: CanonicalState, max_items: int = 3) -> List[SelectedMemoryItem]:
    # /// selected_memory retrieval remains provisional until memory selection policy is finalized.
    selected: List[SelectedMemoryItem] = []
    for idx, item in enumerate(canonical_state.memory_episodic[-max_items:]):
        selected.append(SelectedMemoryItem(memory_id=f"episodic_{idx}", memory_summary=item.event_summary))
    if not selected and canonical_state.memory_working.last_turn_summary:
        selected.append(SelectedMemoryItem(memory_id="working_last_turn", memory_summary=canonical_state.memory_working.last_turn_summary))
    return selected


def build_memory_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta) -> MemoryInput:
    # /// episodic selection window remains provisional until memory retention policy is finalized.
    return MemoryInput(
        schema_version="memory_input.v1",
        task_contract=MemoryTaskContract(node_name="memory", objective="actualizar memoria episódica y de trabajo", success_definition="emitir MemoryOutput mínimo y factual"),
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, 8),
        memory_working_current=canonical_state.memory_working,
        recent_memory_episodic_short=canonical_state.memory_episodic[-4:],
        trace_meta=trace_meta,
    )


def build_planner_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta) -> PlannerInput:
    current_phase = canonical_state.planner_state.current_phase or NegotiationPhase.clima_humano
    phase_card = _select_phase_card(current_phase)
    # /// La selección de phase_card la hace código (lookup por fase), no el modelo planner.
    return PlannerInput(
        schema_version="planner_input.v1",
        task_contract=PlannerTaskContract(node_name="planner", objective="decidir el próximo turno", success_definition="devolver plan mínimo ejecutable sin texto final"),
        persona_policy=canonical_state.persona.policy,
        current_phase=current_phase,
        phase_card=phase_card,
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, 8),
        memory_working=canonical_state.memory_working,
        negotiation_state=canonical_state.negotiation_state,
        planner_state=canonical_state.planner_state,
        selected_memory=_select_memory(canonical_state),
        trace_meta=trace_meta,
    )


def build_executor_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], planner_output: PlannerOutput, user_turn: UserTurn, trace_meta: TraceMeta, max_recent_turns: int) -> ExecutorInput:
    current_phase = canonical_state.planner_state.current_phase or NegotiationPhase.clima_humano
    phase_card = _select_phase_card(current_phase)
    return ExecutorInput(
        schema_version="executor_input.v1",
        task_contract=ExecutorTaskContract(node_name="executor", objective="realizar planner_output sin replanificar", success_definition="respuesta natural dentro de límites"),
        persona_expressive=canonical_state.persona.expressive,
        current_phase=current_phase,
        phase_card=phase_card,
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, max_recent_turns * 2),
        planner_output=planner_output,
        selected_memory_for_reference=_select_memory(canonical_state, max_items=2),
        response_limits=ExecutorResponseLimits(
            max_sentences=planner_output.limits.max_sentences,
            max_questions=planner_output.limits.max_questions,
            allow_topic_shift=planner_output.limits.allow_topic_shift,
            allow_personal_disclosure=planner_output.limits.allow_personal_disclosure,
        ),
        trace_meta=trace_meta,
    )


def build_memory_messages(memory_prompt: str, payload: MemoryInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": memory_prompt}, {"role": "user", "content": payload.model_dump_json()}]


def build_planner_messages(planner_prompt: str, payload: PlannerInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": planner_prompt}, {"role": "user", "content": payload.model_dump_json()}]


def build_phase_classifier_messages_payload(phase_classifier_prompt: str, payload: PhaseClassifierInput) -> List[dict[str, str]]:
    return build_phase_classifier_messages(phase_classifier_prompt, payload)


def build_executor_messages(executor_prompt: str, payload: ExecutorInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": executor_prompt}, {"role": "user", "content": payload.model_dump_json()}]


# ==================================================
# B) Llamadas a OpenAI
# ==================================================

def _build_client() -> openai.OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("openai_api_key_missing negotiation_pipeline_fallback=true")
        return None
    try:
        return openai.OpenAI()
    except Exception as exc:
        logger.warning("openai_client_init_error=%s", exc)
        return None


def _extract_refusal_text(response: object) -> str | None:
    refusal = getattr(response, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return refusal.strip()
    return None


def _call_structured(
    client: openai.OpenAI | None,
    model: str,
    messages: List[dict[str, str]],
    response_model: type[BaseModel],
    reasoning_effort: str,
    request_context: dict[str, str],
    store: bool,
) -> StructuredCallResult:
    if client is None:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=None, exception_error="client_unavailable", response=None, source=StructuredCallSource.fallback)

    kwargs = {
        "model": model,
        "input": messages,
        "text": {"format": {"type": "json_schema", "name": response_model.__name__, "schema": response_model.model_json_schema(), "strict": True}},
        "reasoning": {"effort": reasoning_effort},
        "store": store,
        **request_context,
    }

    try:
        response = client.responses.create(**kwargs)
    except Exception as exc:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=None, exception_error=str(exc), response=None, source=StructuredCallSource.exception)

    refusal = _extract_refusal_text(response)
    if refusal:
        return StructuredCallResult(parsed_json=None, refusal=refusal, parse_error=None, exception_error=None, response=response, source=StructuredCallSource.refusal)

    output_text = getattr(response, "output_text", "")
    try:
        parsed_json = json.loads(output_text or "{}")
        response_model.model_validate(parsed_json)
    except Exception as exc:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=str(exc), exception_error=None, response=response, source=StructuredCallSource.parse_error)

    return StructuredCallResult(parsed_json=parsed_json, refusal=None, parse_error=None, exception_error=None, response=response, source=StructuredCallSource.model)


# ==================================================
# C) Gestión del hilo conversacional
# ==================================================

def check_openai_sdk_compatibility(strict: bool = False) -> SDKCompatibilityInfo:
    try:
        installed = metadata.version("openai")
    except metadata.PackageNotFoundError:
        info = SDKCompatibilityInfo(installed_version=None, minimum_version=OPENAI_MIN_VERSION, status=SDKCompatibilityStatus.unknown, details="openai package not installed")
        logger.error("openai_sdk_missing min_required=%s", OPENAI_MIN_VERSION)
        return info

    installed_tuple = tuple(int(x) for x in installed.split(".")[:3])
    min_tuple = tuple(int(x) for x in OPENAI_MIN_VERSION.split(".")[:3])
    if installed_tuple < min_tuple:
        msg = f"openai SDK {installed} below minimum {OPENAI_MIN_VERSION}"
        logger.error("openai_sdk_incompatible installed=%s min_required=%s strict=%s", installed, OPENAI_MIN_VERSION, strict)
        if strict:
            raise RuntimeError(msg)
        return SDKCompatibilityInfo(installed_version=installed, minimum_version=OPENAI_MIN_VERSION, status=SDKCompatibilityStatus.below_minimum, details=msg)

    return SDKCompatibilityInfo(installed_version=installed, minimum_version=OPENAI_MIN_VERSION, status=SDKCompatibilityStatus.compatible, details="ok")


def bootstrap_conversation_if_needed(client: openai.OpenAI | None, canonical_state: CanonicalState) -> None:
    thread = canonical_state.openai_thread
    if thread.thread_mode != ThreadMode.conversation or thread.conversation_id:
        return
    if client is None:
        logger.info("conversation_bootstrap_skipped_no_client")
        return
    try:
        conversation = client.conversations.create()
        conversation_id = getattr(conversation, "id", None)
        if isinstance(conversation_id, str) and conversation_id:
            thread.conversation_id = conversation_id
    except Exception as exc:
        logger.error("conversation_bootstrap_exception error=%s", exc)


def ensure_openai_thread(client: openai.OpenAI | None, canonical_state: CanonicalState, mode_default: ThreadMode) -> OpenAIThreadState:
    _ = mode_default  # compatible signature: el modo efectivo lo define el canónico válido.
    bootstrap_conversation_if_needed(client, canonical_state)
    return canonical_state.openai_thread


def build_openai_request_context(thread: OpenAIThreadState) -> dict[str, str]:
    if thread.thread_mode == ThreadMode.conversation and thread.conversation_id:
        return {"conversation": thread.conversation_id}
    if thread.thread_mode == ThreadMode.previous_response_id and thread.previous_response_id:
        return {"previous_response_id": thread.previous_response_id}
    return {}


def update_thread_after_response(thread: OpenAIThreadState, response: object) -> None:
    response_id = getattr(response, "id", None)
    if thread.thread_mode == ThreadMode.previous_response_id and isinstance(response_id, str):
        thread.previous_response_id = response_id
    if thread.thread_mode == ThreadMode.conversation:
        conv = getattr(response, "conversation", None)
        conversation_id = getattr(conv, "id", None)
        if isinstance(conversation_id, str):
            thread.conversation_id = conversation_id


def refresh_request_context(client: openai.OpenAI | None, canonical_state: CanonicalState, mode_default: ThreadMode) -> dict[str, str]:
    thread = ensure_openai_thread(client, canonical_state, mode_default)
    return build_openai_request_context(thread)


# ==================================================
# D) Aplicación de cambios al estado
# ==================================================

def apply_memory_output_to_state(canonical_state: CanonicalState, output: MemoryOutput) -> None:
    # updated by memory node
    # /// final deduplication policy depends on unresolved memory selection policy.
    canonical_state.memory_episodic.extend(
        [MemoryEpisodicItem(event_type=item.event_type, event_summary=item.summary, turn_id=item.turn_id) for item in output.episodic_append]
    )
    # refreshed each turn from memory output
    canonical_state.memory_working.current_topic = output.working_memory_new.current_topic
    canonical_state.memory_working.pending_question = output.working_memory_new.pending_question
    canonical_state.memory_working.last_turn_summary = output.working_memory_new.last_turn_summary


def apply_planner_output_to_state(canonical_state: CanonicalState, planner_output: PlannerOutput) -> None:
    canonical_state.planner_state.current_turn_goal = planner_output.turn_goal


def apply_phase_classifier_output_to_state(canonical_state: CanonicalState, phase_output: PhaseClassifierOutput) -> None:
    canonical_state.planner_state.previous_phase = canonical_state.planner_state.current_phase
    canonical_state.planner_state.current_phase = phase_output.current_phase
    # /// La lógica de mover tópicos entre current/previous phases depende del contrato final planner-memory y no se define aquí.


# ==================================================
# E) Guardarraíles
# ==================================================

def _contains_pii(text: str) -> bool:
    return any(signal in text.lower() for signal in ["dni", "pasaporte", "tarjeta", "cuenta bancaria", "iban", "cvv"])


def _contains_overclaim(text: str) -> bool:
    return any(signal in text.lower() for signal in ["garantizo", "100% seguro", "sin duda"])


def _contains_critical_domain(text: str) -> SafetyDomain:
    lower = text.lower()
    if any(t in lower for t in ["diagnóstico", "medicina", "tratamiento", "síntoma"]):
        return SafetyDomain.medical
    if any(t in lower for t in ["demanda", "abogado", "juicio", "ilegal"]):
        return SafetyDomain.legal
    if any(t in lower for t in ["inversión", "acciones", "cripto", "rendimiento garantizado"]):
        return SafetyDomain.financial
    if any(t in lower for t in ["hackea", "arma", "explosivo", "veneno"]):
        return SafetyDomain.dangerous_instruction
    return SafetyDomain.none


def _safety_policy(config: NegotiationTurnConfig) -> SafetyPolicyConfig:
    return SafetyPolicyConfig(hard_baseline_enabled=True, optional_layer_enabled=config.feature_safety)


def _apply_executor_guardrails(executor_output: ExecutorOutput, planner_output: PlannerOutput, user_turn: UserTurn, policy: SafetyPolicyConfig) -> Tuple[ExecutorOutput, str | None]:
    if not policy.optional_layer_enabled:
        return executor_output, None

    domain = _contains_critical_domain(user_turn.normalized_text)
    if domain != SafetyDomain.none:
        return executor_output.model_copy(update={
            "status": "clarify",
            "spoken_text": "Puedo ayudarte de forma general, pero no puedo dar asesoría profesional específica en ese ámbito.",
            "refusal_reason": f"domain_restriction:{domain.value}",
        }), "optional_domain_guardrail"

    if _contains_pii(executor_output.spoken_text) or _contains_overclaim(executor_output.spoken_text):
        return executor_output.model_copy(update={
            "status": "clarify",
            "spoken_text": "Prefiero mantener precisión y seguridad. ¿Quieres que lo formule de forma más cauta?",
            "refusal_reason": "safety_rewrite_required",
        }), "optional_output_guardrail"

    return executor_output, None


# ==================================================
# F) Trazas y evaluación
# ==================================================

def _evaluate_stub(planner: PlannerOutput, executor: ExecutorOutput) -> EvalGrades:
    aligned = (
        (planner.status == "refuse" and executor.status == "refuse")
        or (planner.status == "clarify" and executor.status == "clarify")
        or (planner.status == "plan" and executor.status in {"deliver", "clarify"})
    )
    return EvalGrades(
        planner_coherence="pending",
        executor_naturalness="pending",
        planner_executor_agreement=aligned,
        safety_compliance=executor.status != "refuse" or bool(executor.refusal_reason),
    )


def _trace_input_summary(messages: Sequence[MemoryDialogueMessage], user_turn: UserTurn) -> InputSummary:
    return InputSummary(user_turn_chars=len(user_turn.normalized_text), recent_dialogue_items=len(messages))


def _build_trace_log(node: NodeName, model: str, prompt_version: str, schema_version: str, latency_ms: int, input_summary: InputSummary, output_status: str, call_result: StructuredCallResult, error: ErrorSummary | None) -> NodeTraceLog:
    return NodeTraceLog(
        node=node,
        model=model,
        prompt_version=prompt_version,
        schema_version=schema_version,
        latency_ms=latency_ms,
        retries=0,
        input_summary=input_summary,
        output_status=output_status,
        call_source=call_result.source,
        refusal=call_result.refusal,
        parse_error=call_result.parse_error,
        error=error,
    )


def _append_unique_reason(container: list[str], reason: str | None) -> None:
    if not reason:
        return
    value = reason.strip()
    if value and value not in container:
        container.append(value)


def _collect_last_refusals(logs: Sequence[NodeTraceLog], executor_output: ExecutorOutput, guardrail_reason: str | None) -> list[str]:
    reasons: list[str] = []
    for log in logs:
        _append_unique_reason(reasons, log.refusal)
    _append_unique_reason(reasons, executor_output.refusal_reason)
    _append_unique_reason(reasons, guardrail_reason)
    return reasons


def _resolve_memory_call_result(canonical_state: CanonicalState, turn_id: str, mem_call: StructuredCallResult) -> MemoryOutput:
    if mem_call.source == StructuredCallSource.model and mem_call.parsed_json is not None:
        return MemoryOutput.model_validate(mem_call.parsed_json)
    return _memory_fallback(canonical_state, turn_id)


def _resolve_phase_call_result(canonical_state: CanonicalState, phase_call: StructuredCallResult) -> PhaseClassifierOutput:
    if phase_call.source == StructuredCallSource.model and phase_call.parsed_json is not None:
        return PhaseClassifierOutput.model_validate(phase_call.parsed_json)
    return _phase_classifier_fallback(canonical_state.planner_state.current_phase)


def _execute_memory_and_phase(
    *,
    client: openai.OpenAI | None,
    config: NegotiationTurnConfig,
    canonical_state: CanonicalState,
    request_context: dict[str, str],
    memory_prompt: str,
    phase_classifier_prompt: str,
    memory_input: MemoryInput,
    phase_input: PhaseClassifierInput,
) -> tuple[StructuredCallResult, int, StructuredCallResult, int, dict[str, str]]:
    """Run memory+phase with explicit threading mode semantics.

    - conversation: parallel allowed
    - previous_response_id: forced sequential to preserve deterministic parent chain
    """

    def _run_memory_call(ctx: dict[str, str]) -> tuple[StructuredCallResult, int]:
        mem_start = time.perf_counter()
        call = _call_structured(
            client,
            config.model_memory,
            build_memory_messages(memory_prompt, memory_input),
            MemoryOutput,
            "low",
            ctx,
            config.memory_store,
        )
        latency = int((time.perf_counter() - mem_start) * 1000)
        return call, latency

    def _run_phase_call(ctx: dict[str, str]) -> tuple[StructuredCallResult, int]:
        phase_start = time.perf_counter()
        call = _call_structured(
            client,
            config.model_phase_classifier,
            build_phase_classifier_messages_payload(phase_classifier_prompt, phase_input),
            PhaseClassifierOutput,
            "low",
            ctx,
            config.memory_store,
        )
        latency = int((time.perf_counter() - phase_start) * 1000)
        return call, latency

    if canonical_state.openai_thread.thread_mode == ThreadMode.previous_response_id:
        # No paralelizar ramas que compartan el mismo parent previous_response_id.
        mem_call, mem_latency = _run_memory_call(request_context)
        if mem_call.response is not None:
            update_thread_after_response(canonical_state.openai_thread, mem_call.response)
        request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)

        phase_call, phase_latency = _run_phase_call(request_context)
        if phase_call.response is not None:
            update_thread_after_response(canonical_state.openai_thread, phase_call.response)
        request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
        return mem_call, mem_latency, phase_call, phase_latency, request_context

    with ThreadPoolExecutor(max_workers=2) as executor:
        mem_future = executor.submit(_run_memory_call, request_context)
        phase_future = executor.submit(_run_phase_call, request_context)
        mem_call, mem_latency = mem_future.result()
        phase_call, phase_latency = phase_future.result()

    if mem_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, mem_call.response)
    if phase_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, phase_call.response)
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    return mem_call, mem_latency, phase_call, phase_latency, request_context


def _memory_fallback(canonical_state: CanonicalState, turn_id: str) -> MemoryOutput:
    return MemoryOutput(
        schema_version="memory.v1",
        episodic_append=[],
        working_memory_new=MemoryWorkingOutput(
            current_topic=canonical_state.memory_working.current_topic,
            pending_question=canonical_state.memory_working.pending_question,
            last_turn_summary=canonical_state.memory_working.last_turn_summary or f"turn {turn_id}: sin cambios de memoria",
        ),
    )


def _phase_classifier_fallback(previous_phase: NegotiationPhase | None) -> PhaseClassifierOutput:
    return PhaseClassifierOutput(current_phase=previous_phase or NegotiationPhase.clima_humano)


def _planner_fallback(status: str = "plan", refusal_reason: str | None = None) -> PlannerOutput:
    decision = "none" if status == "plan" else "clarify" if status == "clarify" else "reject"
    note = "rechazo" if status == "refuse" else "aclaración" if status == "clarify" else "respuesta"
    return PlannerOutput(
        schema_version="planner.v3",
        status=status,
        turn_goal="responder con claridad",
        decision=decision,
        content_plan=PlannerContentPlan(must_include=["una respuesta útil"], must_avoid=["inventar hechos"]),
        limits=PlannerLimits(max_sentences=4, max_questions=1, allow_topic_shift=False, allow_personal_disclosure=False),
        memory_targets=[],
        done_criteria=[f"{note}_emitida"],
    )


def _executor_fallback(planner_output: PlannerOutput, status: str | None = None, refusal_reason: str | None = None) -> ExecutorOutput:
    resolved_status = status or ("refuse" if planner_output.status == "refuse" else "clarify" if planner_output.status == "clarify" else "deliver")
    text = "No puedo ayudar con esa solicitud." if resolved_status == "refuse" else "Necesito un dato adicional para continuar." if resolved_status == "clarify" else "Entiendo. Te respondo de forma clara y directa."
    return ExecutorOutput(
        schema_version="executor.v1",
        status=resolved_status,
        spoken_text=text,
        memory_used=[],
        refusal_reason=refusal_reason,
    )


def _read_text(path: Path, fallback: str) -> str:
    if not path.exists():
        return fallback
    text = path.read_text(encoding="utf-8").strip()
    return text if text else fallback


# ==================================================
# Pipeline principal del turno
# ==================================================

def run_negotiation_cognitive_turn(state: SessionState, user_message: str, config: NegotiationTurnConfig) -> Tuple[str, SessionState]:
    sdk_info = check_openai_sdk_compatibility(strict=config.enforce_sdk_compatibility)

    repo = StateRepository(memory_key=config.memory_key)
    canonical_state = repo.load_state(state, thread_mode=config.thread_mode_default)
    recent_dialogue = repo.load_recent_dialogue(state)

    turn_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    memory_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_memory, schema_version="memory_input.v1", model_target=config.model_memory)
    phase_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_phase_classifier, schema_version=PHASE_CLASSIFIER_INPUT_SCHEMA_VERSION, model_target=config.model_phase_classifier)
    planner_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_planner, schema_version="planner_input.v1", model_target=config.model_planner)
    executor_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_executor, schema_version="executor_input.v1", model_target=config.model_executor)
    user_turn = _build_user_turn(user_message, now_iso)

    add_message(state, role="user", content=user_message)
    recent_dialogue.append(MemoryDialogueMessage(role="user", text=user_turn.normalized_text))
    recent_dialogue = _compact_recent(recent_dialogue, config.max_recent_messages)

    prompts_dir = Path(config.prompts_dir)
    memory_prompt = _read_text(prompts_dir / "summarizer_prompt.txt", "Identity: memory node\nOutput: MemoryOutput JSON estricto")
    phase_classifier_prompt = _read_text(prompts_dir / "phase_classifier_prompt.txt", "Clasifica la fase conversacional actual y devuelve SOLO current_phase en JSON estricto.")
    planner_prompt = _read_text(prompts_dir / "planner_prompt.txt", "[ROLE] planner\n[CONTRACT] return only PlannerOutput json\n[SUCCESS] strong intent, limits and safety")
    executor_prompt = _read_text(prompts_dir / "executor_prompt.txt", "[ROLE] executor\n[CONTRACT] return only ExecutorOutput json\n[SUCCESS] realize planner without replanning")

    client = _build_client()
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    logs: List[NodeTraceLog] = []
    safety_policy = _safety_policy(config)

    memory_input = build_memory_input(canonical_state, recent_dialogue, user_turn, memory_trace_meta)
    phase_input = build_phase_input(canonical_state, recent_dialogue, user_turn, phase_trace_meta)
    mem_call, mem_latency, phase_call, phase_latency, request_context = _execute_memory_and_phase(
        client=client,
        config=config,
        canonical_state=canonical_state,
        request_context=request_context,
        memory_prompt=memory_prompt,
        phase_classifier_prompt=phase_classifier_prompt,
        memory_input=memory_input,
        phase_input=phase_input,
    )

    memory_patch = _resolve_memory_call_result(canonical_state, turn_id, mem_call)
    phase_output = _resolve_phase_call_result(canonical_state, phase_call)

    apply_memory_output_to_state(canonical_state, memory_patch)
    apply_phase_classifier_output_to_state(canonical_state, phase_output)
    logs.append(_build_trace_log(NodeName.memory, config.model_memory, config.prompt_version_memory, memory_patch.schema_version, mem_latency, _trace_input_summary(memory_input.recent_dialogue_short, user_turn), "applied", mem_call, None))
    logs.append(_build_trace_log(NodeName.phase_classifier, config.model_phase_classifier, config.prompt_version_phase_classifier, "phase_classifier_output_v1", phase_latency, _trace_input_summary(phase_input.recent_turns, user_turn), phase_output.current_phase.value, phase_call, None))

    planner_input = build_planner_input(canonical_state, recent_dialogue, user_turn, planner_trace_meta)
    plan_start = time.perf_counter()
    planner_call = _call_structured(client, config.model_planner, build_planner_messages(planner_prompt, planner_input), PlannerOutput, config.reasoning_effort_planner, request_context, config.planner_store)
    planner_output = _planner_fallback()
    if planner_call.source == StructuredCallSource.model and planner_call.parsed_json is not None:
        planner_output = PlannerOutput.model_validate(planner_call.parsed_json)
    elif planner_call.source == StructuredCallSource.refusal:
        planner_output = _planner_fallback(status="refuse", refusal_reason=planner_call.refusal)
    plan_latency = int((time.perf_counter() - plan_start) * 1000)

    apply_planner_output_to_state(canonical_state, planner_output)
    if planner_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, planner_call.response)
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    logs.append(_build_trace_log(NodeName.planner, config.model_planner, config.prompt_version_planner, planner_output.schema_version, plan_latency, _trace_input_summary(planner_input.recent_dialogue_short, user_turn), planner_output.status, planner_call, None))

    executor_input = build_executor_input(canonical_state, recent_dialogue, planner_output, user_turn, executor_trace_meta, config.max_executor_recent_turns)
    exe_start = time.perf_counter()
    executor_call = _call_structured(client, config.model_executor, build_executor_messages(executor_prompt, executor_input), ExecutorOutput, "low", request_context, config.executor_store)
    executor_output = _executor_fallback(planner_output)
    if executor_call.source == StructuredCallSource.model and executor_call.parsed_json is not None:
        executor_output = ExecutorOutput.model_validate(executor_call.parsed_json)
    elif executor_call.source == StructuredCallSource.refusal:
        executor_output = _executor_fallback(planner_output, status="refuse", refusal_reason=executor_call.refusal)
    exe_latency = int((time.perf_counter() - exe_start) * 1000)

    executor_output, enforcement_reason = _apply_executor_guardrails(executor_output, planner_output, user_turn, safety_policy)
    if executor_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, executor_call.response)
    logs.append(_build_trace_log(NodeName.executor, config.model_executor, config.prompt_version_executor, executor_output.schema_version, exe_latency, _trace_input_summary(executor_input.recent_dialogue_short, user_turn), executor_output.status if enforcement_reason is None else f"{executor_output.status}:{enforcement_reason}", executor_call, None))

    reply = executor_output.spoken_text
    add_message(state, role="assistant", content=reply)
    recent_dialogue.append(MemoryDialogueMessage(role="assistant", text=reply))
    recent_dialogue = _compact_recent(recent_dialogue, config.max_recent_messages)

    grades = _evaluate_stub(planner_output, executor_output) if config.feature_eval_hooks else EvalGrades(planner_coherence="disabled", executor_naturalness="disabled", planner_executor_agreement=True, safety_compliance=True)
    turn_trace = TurnTrace(
        turn_id=turn_id,
        timestamp_utc=now_iso,
        model_memory=config.model_memory,
        model_phase_classifier=config.model_phase_classifier,
        model_planner=config.model_planner,
        model_executor=config.model_executor,
        prompt_version_memory=config.prompt_version_memory,
        prompt_version_phase_classifier=config.prompt_version_phase_classifier,
        prompt_version_planner=config.prompt_version_planner,
        prompt_version_executor=config.prompt_version_executor,
        schema_version_memory=memory_patch.schema_version,
        schema_version_phase_classifier="phase_classifier_output_v1",
        schema_version_planner=planner_output.schema_version,
        schema_version_executor=executor_output.schema_version,
        sdk_compatibility=sdk_info,
        grades=grades,
        logs=logs,
    )

    canonical_state.trace.turn_id = turn_trace.turn_id
    canonical_state.trace.last_node_statuses = {log.node.value: log.output_status for log in logs}
    canonical_state.trace.last_fallbacks = [log.node.value for log in logs if log.call_source != StructuredCallSource.model]
    canonical_state.trace.last_refusals = _collect_last_refusals(logs, executor_output, enforcement_reason)
    repo.save_state(state, canonical_state)
    repo.save_recent_dialogue(state, recent_dialogue)
    if config.feature_traces:
        repo.append_trace(state, turn_trace)

    save_session_state(state)
    return reply, state
