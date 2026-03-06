from __future__ import annotations

import json
import logging
import os
import time
import uuid
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
    DialogueMessage,
    MemoryEpisode,
    MemoryProfile,
    MemoryWorking,
    OpenAIThreadState,
    PersonaExpressive,
    PersonaPolicy,
    PersonaState,
    PlanState,
    RelationshipState,
    SafetyState,
    SessionSettings,
    VoiceState,
)
from .executor_node import (
    ExecutorInput,
    ExecutorOutput,
    ExecutorSafetyLimits,
    ExecutorTTS,
    MemoryForUse,
    TaskContractExecutor,
    TTSHints,
)
from .memory_node import MemoryInput, MemoryPatch, TraceMeta, UserTurn
from .planner_node import (
    ExternalEvidenceItem,
    PlannerContentPlan,
    PlannerInput,
    PlannerLimits,
    PlannerOutput,
    PlannerPolicy,
    PlannerSafety,
    PlannerSituation,
    PlannerStyleBand,
    SelectedMemory,
    TaskContractPlanner,
)
from .shared_types import (
    ConversationAct,
    DirectnessLevel,
    EmotionalIntensity,
    ExecutorStatus,
    InitiativeLevel,
    LengthBand,
    NodeName,
    PlannerStatus,
    SDKCompatibilityStatus,
    SafetyDomain,
    SafetyPolicyAction,
    SafetyRiskLevel,
    StructuredCallSource,
    StyleTone,
    ThreadMode,
)

logger = logging.getLogger(__name__)

OPENAI_MIN_VERSION = "1.40.0"


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
    model_planner: str
    model_executor: str
    prompt_version_memory: str
    prompt_version_planner: str
    prompt_version_executor: str
    schema_version_memory: str
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
    prompt_version_planner: str = "planner_v3"
    prompt_version_executor: str = "executor_v3"
    enforce_sdk_compatibility: bool = False


class FlowDetails(TypedDict):
    flow_name: str
    memory_key: str
    model_memory: str
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

    def load_state(self, session_state: SessionState) -> CanonicalState:
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
        return _default_canonical_state()

    def save_state(self, session_state: SessionState, canonical_state: CanonicalState) -> None:
        session_state.world_state[self.memory_key] = canonical_state.model_dump(mode="json")

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


def _default_canonical_state() -> CanonicalState:
    return CanonicalState(
        session_settings=SessionSettings(thread_mode_override=None),
        openai_thread=OpenAIThreadState(mode=ThreadMode.conversation, conversation_id=None, previous_response_id=None),
        recent_messages=[],
        persona=PersonaState(
            policy=PersonaPolicy(role_identity="negotiador", negotiation_goal="avanzar negociación con claridad", question_strategy="minimal", allow_topic_shift=False),
            expressive=PersonaExpressive(tone=StyleTone.neutral, lexical_style="plain", max_sentences_default=4),
        ),
        relationship=RelationshipState(trust_level="medium", rapport_level="medium", last_interaction_note=None),
        memory_profile=MemoryProfile(user_name=None, preferred_language="es", risk_tolerance="medium"),
        memory_episodic=[],
        memory_working=MemoryWorking(current_user_goal=None, pending_question=None, negotiation_stage="unknown"),
        plan=PlanState(current_status=PlannerStatus.plan, current_act=ConversationAct.answer, current_goal="help_user"),
        safety=SafetyState(risk_level=SafetyRiskLevel.low, active_domain=SafetyDomain.none, action=SafetyPolicyAction.allow, reason=None),
        voice=VoiceState(voice_name="cedar", speed="normal"),
        trace=None,
    )


# ==================================================
# A) Construcción de contexto
# ==================================================

def _build_user_turn(user_message: str, now_iso: str) -> UserTurn:
    normalized = " ".join(user_message.strip().split())
    return UserTurn(raw_text=user_message, normalized_text=normalized, modality="text", language="es", timestamp_utc=now_iso)


def _compact_recent(recent: Sequence[DialogueMessage], max_messages: int) -> List[DialogueMessage]:
    return list(recent[-max_messages:])


def _select_memory(canonical_state: CanonicalState) -> SelectedMemory:
    return SelectedMemory(
        profile=canonical_state.memory_profile,
        working=canonical_state.memory_working,
        episodic_recent=canonical_state.memory_episodic[-3:],
    )


def build_memory_input(canonical_state: CanonicalState, user_turn: UserTurn, trace_meta: TraceMeta) -> MemoryInput:
    return MemoryInput(
        task_contract=TaskContractPlanner(single_visible_persona=True, executor_cannot_replan=True, success_definition="actualizar memoria incremental"),
        relationship_state=canonical_state.relationship,
        memory_profile=canonical_state.memory_profile,
        memory_working=canonical_state.memory_working,
        recent_dialogue=_compact_recent(canonical_state.recent_messages, 8),
        user_turn=user_turn,
        trace_meta=trace_meta,
    )


def build_planner_input(canonical_state: CanonicalState, user_turn: UserTurn, trace_meta: TraceMeta) -> PlannerInput:
    return PlannerInput(
        task_contract=TaskContractPlanner(single_visible_persona=True, executor_cannot_replan=True, success_definition="definir intención, acto conversacional, límites y safety del turno"),
        persona_policy=canonical_state.persona.policy,
        relationship_state=canonical_state.relationship,
        working_state=canonical_state.memory_working,
        recent_dialogue=_compact_recent(canonical_state.recent_messages, 8),
        selected_memory=_select_memory(canonical_state),
        external_evidence=[],
        user_turn=user_turn,
        safety_flags=canonical_state.safety,
        trace_meta=trace_meta,
    )


def build_executor_input(canonical_state: CanonicalState, planner_output: PlannerOutput, user_turn: UserTurn, trace_meta: TraceMeta, max_recent_turns: int) -> ExecutorInput:
    return ExecutorInput(
        task_contract=TaskContractExecutor(must_realize_planner_output=True, cannot_change_conversation_act=True),
        expressive_persona=canonical_state.persona.expressive,
        planner_output=planner_output,
        recent_dialogue_short=_compact_recent(canonical_state.recent_messages, max_recent_turns * 2),
        user_turn=user_turn,
        memory_for_use=MemoryForUse(
            profile_snippet=canonical_state.memory_profile,
            working_snippet=canonical_state.memory_working,
            episodic_snippet=canonical_state.memory_episodic[-2:],
        ),
        safety_limits=ExecutorSafetyLimits(action=planner_output.safety.policy_action, blocked_domains=planner_output.safety.blocked_domains, overclaim_block=True),
        tts_hints=TTSHints(voice_name=canonical_state.voice.voice_name, speaking_speed=canonical_state.voice.speed),
        style_examples=[],
        trace_meta=trace_meta,
    )


def build_memory_messages(memory_prompt: str, payload: MemoryInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": memory_prompt}, {"role": "user", "content": payload.model_dump_json()}]


def build_planner_messages(planner_prompt: str, payload: PlannerInput) -> List[dict[str, str]]:
    return [{"role": "developer", "content": planner_prompt}, {"role": "user", "content": payload.model_dump_json()}]


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


def _resolve_structured_result(result: StructuredCallResult, response_model: type[BaseModel], fallback: BaseModel) -> BaseModel:
    if result.source == StructuredCallSource.model and result.parsed_json is not None:
        return response_model.model_validate(result.parsed_json)
    return fallback


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
    if thread.mode != ThreadMode.conversation or thread.conversation_id:
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
    mode = canonical_state.session_settings.thread_mode_override or mode_default
    if canonical_state.openai_thread.mode != mode:
        canonical_state.openai_thread = OpenAIThreadState(mode=mode, conversation_id=None, previous_response_id=None)
    bootstrap_conversation_if_needed(client, canonical_state)
    return canonical_state.openai_thread


def build_openai_request_context(thread: OpenAIThreadState) -> dict[str, str]:
    if thread.mode == ThreadMode.conversation and thread.conversation_id:
        return {"conversation": thread.conversation_id}
    if thread.mode == ThreadMode.previous_response_id and thread.previous_response_id:
        return {"previous_response_id": thread.previous_response_id}
    return {}


def update_thread_after_response(thread: OpenAIThreadState, response: object) -> None:
    response_id = getattr(response, "id", None)
    if thread.mode == ThreadMode.previous_response_id and isinstance(response_id, str):
        thread.previous_response_id = response_id
    if thread.mode == ThreadMode.conversation:
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

def apply_memory_patch(canonical_state: CanonicalState, patch: MemoryPatch) -> None:
    if patch.profile_user_name is not None:
        canonical_state.memory_profile.user_name = patch.profile_user_name
    if patch.profile_preferred_language is not None:
        canonical_state.memory_profile.preferred_language = patch.profile_preferred_language
    if patch.profile_risk_tolerance is not None:
        canonical_state.memory_profile.risk_tolerance = patch.profile_risk_tolerance
    if patch.working_current_user_goal is not None:
        canonical_state.memory_working.current_user_goal = patch.working_current_user_goal
    if patch.working_pending_question is not None:
        canonical_state.memory_working.pending_question = patch.working_pending_question
    if patch.working_negotiation_stage is not None:
        canonical_state.memory_working.negotiation_stage = patch.working_negotiation_stage
    if patch.relationship_trust_level is not None:
        canonical_state.relationship.trust_level = patch.relationship_trust_level
    if patch.relationship_rapport_level is not None:
        canonical_state.relationship.rapport_level = patch.relationship_rapport_level
    if patch.relationship_last_interaction_note is not None:
        canonical_state.relationship.last_interaction_note = patch.relationship_last_interaction_note
    if patch.safety_risk_level is not None:
        canonical_state.safety.risk_level = patch.safety_risk_level
    if patch.safety_active_domain is not None:
        canonical_state.safety.active_domain = patch.safety_active_domain
    if patch.safety_action is not None:
        canonical_state.safety.action = patch.safety_action
    if patch.safety_reason is not None:
        canonical_state.safety.reason = patch.safety_reason
    canonical_state.memory_episodic.extend(patch.episodic_append)


def apply_planner_output_to_state(canonical_state: CanonicalState, planner_output: PlannerOutput) -> None:
    canonical_state.plan = PlanState(current_status=planner_output.status, current_act=planner_output.policy.conversation_act, current_goal=planner_output.policy.turn_goal)


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


def _apply_optional_safety_to_memory_patch(patch: MemoryPatch, policy: SafetyPolicyConfig) -> MemoryPatch:
    if not policy.optional_layer_enabled:
        return patch
    safe_name = None if patch.profile_user_name and _contains_pii(patch.profile_user_name) else patch.profile_user_name
    return patch.model_copy(update={"profile_user_name": safe_name})


def _apply_executor_guardrails(executor_output: ExecutorOutput, planner_output: PlannerOutput, user_turn: UserTurn, policy: SafetyPolicyConfig) -> Tuple[ExecutorOutput, str | None]:
    if executor_output.conversation_act_realized != planner_output.policy.conversation_act:
        return executor_output.model_copy(update={
            "status": ExecutorStatus.clarify,
            "conversation_act_realized": planner_output.policy.conversation_act,
            "spoken_text": "Para mantener coherencia, confirmo el objetivo del turno antes de continuar. ¿Quieres que siga por ese camino?",
            "refusal_reason": "executor_replan_blocked",
        }), "executor_replan_blocked"

    if not policy.optional_layer_enabled:
        return executor_output, None

    domain = _contains_critical_domain(user_turn.normalized_text)
    if domain != SafetyDomain.none:
        return executor_output.model_copy(update={
            "status": ExecutorStatus.clarify,
            "spoken_text": "Puedo ayudarte de forma general, pero no puedo dar asesoría profesional específica en ese ámbito.",
            "refusal_reason": f"domain_restriction:{domain.value}",
        }), "optional_domain_guardrail"

    if _contains_pii(executor_output.spoken_text) or _contains_overclaim(executor_output.spoken_text):
        return executor_output.model_copy(update={
            "status": ExecutorStatus.clarify,
            "spoken_text": "Prefiero mantener precisión y seguridad. ¿Quieres que lo formule de forma más cauta?",
            "refusal_reason": "safety_rewrite_required",
        }), "optional_output_guardrail"

    return executor_output, None


# ==================================================
# F) Trazas y evaluación
# ==================================================

def _evaluate_stub(planner: PlannerOutput, executor: ExecutorOutput) -> EvalGrades:
    return EvalGrades(
        planner_coherence="pending",
        executor_naturalness="pending",
        planner_executor_agreement=planner.policy.conversation_act == executor.conversation_act_realized,
        safety_compliance=executor.status != ExecutorStatus.refuse or bool(executor.refusal_reason),
    )


def _trace_input_summary(messages: Sequence[DialogueMessage], user_turn: UserTurn) -> InputSummary:
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


def _memory_fallback() -> MemoryPatch:
    return MemoryPatch(
        schema_version="memory_patch_v3",
        profile_user_name=None,
        profile_preferred_language=None,
        profile_risk_tolerance=None,
        episodic_append=[],
        working_current_user_goal=None,
        working_pending_question=None,
        working_negotiation_stage=None,
        relationship_trust_level=None,
        relationship_rapport_level=None,
        relationship_last_interaction_note=None,
        safety_risk_level=None,
        safety_active_domain=None,
        safety_action=None,
        safety_reason=None,
    )


def _planner_fallback(status: PlannerStatus = PlannerStatus.plan, refusal_reason: str | None = None) -> PlannerOutput:
    action = SafetyPolicyAction.refuse if status == PlannerStatus.refuse else SafetyPolicyAction.allow
    return PlannerOutput(
        schema_version="planner_output_v3",
        status=status,
        situation=PlannerSituation(user_intent="general_help", user_emotion="unknown"),
        policy=PlannerPolicy(conversation_act=ConversationAct.answer if status != PlannerStatus.refuse else ConversationAct.refuse, turn_goal="responder con claridad", ask_clarification=False),
        content_plan=PlannerContentPlan(key_points=["Responder útilmente"], forbidden_topics=[]),
        style_band=PlannerStyleBand(tone=StyleTone.neutral, length_band=LengthBand.medium, directness=DirectnessLevel.balanced, initiative=InitiativeLevel.balanced, emotional_intensity=EmotionalIntensity.low),
        limits=PlannerLimits(max_sentences=4, max_questions=1, allow_topic_shift=False, allow_advice=False, allow_personal_disclosure=False),
        safety=PlannerSafety(risk_level=SafetyRiskLevel.low, policy_action=action, refusal_reason=refusal_reason, blocked_domains=[]),
        done_criteria=["respuesta_emitida"],
    )


def _executor_fallback(planner_output: PlannerOutput, status: ExecutorStatus | None = None, refusal_reason: str | None = None) -> ExecutorOutput:
    resolved_status = status or (ExecutorStatus.refuse if planner_output.status == PlannerStatus.refuse else ExecutorStatus.deliver)
    text = "No puedo ayudar con esa solicitud." if resolved_status == ExecutorStatus.refuse else "Entiendo. Te respondo de forma clara y directa."
    return ExecutorOutput(
        schema_version="executor_output_v3",
        status=resolved_status,
        spoken_text=text,
        conversation_act_realized=planner_output.policy.conversation_act if resolved_status != ExecutorStatus.refuse else ConversationAct.refuse,
        memory_used=[],
        tts=ExecutorTTS(voice_name="cedar", speaking_speed="normal"),
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
    canonical_state = repo.load_state(state)

    turn_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    trace_meta = TraceMeta(turn_id=turn_id, timestamp_utc=now_iso)
    user_turn = _build_user_turn(user_message, now_iso)

    add_message(state, role="user", content=user_message)
    canonical_state.recent_messages.append(DialogueMessage(role="user", content=user_turn.normalized_text))
    canonical_state.recent_messages = _compact_recent(canonical_state.recent_messages, config.max_recent_messages)

    prompts_dir = Path(config.prompts_dir)
    memory_prompt = _read_text(prompts_dir / "summarizer_prompt.txt", "[ROLE] memory updater\n[CONTRACT] return only MemoryPatch json\n[SUCCESS] incremental updates only")
    planner_prompt = _read_text(prompts_dir / "planner_prompt.txt", "[ROLE] planner\n[CONTRACT] return only PlannerOutput json\n[SUCCESS] strong intent, limits and safety")
    executor_prompt = _read_text(prompts_dir / "executor_prompt.txt", "[ROLE] executor\n[CONTRACT] return only ExecutorOutput json\n[SUCCESS] realize planner without replanning")

    client = _build_client()
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    logs: List[NodeTraceLog] = []
    safety_policy = _safety_policy(config)

    memory_input = build_memory_input(canonical_state, user_turn, trace_meta)
    mem_start = time.perf_counter()
    mem_call = _call_structured(client, config.model_memory, build_memory_messages(memory_prompt, memory_input), MemoryPatch, "low", request_context, config.memory_store)
    memory_patch = _resolve_structured_result(mem_call, MemoryPatch, _memory_fallback())
    if mem_call.source != StructuredCallSource.model:
        memory_patch = _memory_fallback()
    mem_latency = int((time.perf_counter() - mem_start) * 1000)

    memory_patch = _apply_optional_safety_to_memory_patch(memory_patch, safety_policy)
    apply_memory_patch(canonical_state, memory_patch)
    if mem_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, mem_call.response)
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    logs.append(_build_trace_log(NodeName.memory, config.model_memory, config.prompt_version_memory, memory_patch.schema_version, mem_latency, _trace_input_summary(memory_input.recent_dialogue, user_turn), "applied", mem_call, None))

    planner_input = build_planner_input(canonical_state, user_turn, trace_meta)
    plan_start = time.perf_counter()
    planner_call = _call_structured(client, config.model_planner, build_planner_messages(planner_prompt, planner_input), PlannerOutput, config.reasoning_effort_planner, request_context, config.planner_store)
    planner_output = _planner_fallback()
    if planner_call.source == StructuredCallSource.model and planner_call.parsed_json is not None:
        planner_output = PlannerOutput.model_validate(planner_call.parsed_json)
    elif planner_call.source == StructuredCallSource.refusal:
        planner_output = _planner_fallback(status=PlannerStatus.refuse, refusal_reason=planner_call.refusal)
    plan_latency = int((time.perf_counter() - plan_start) * 1000)

    apply_planner_output_to_state(canonical_state, planner_output)
    if planner_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, planner_call.response)
    request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    logs.append(_build_trace_log(NodeName.planner, config.model_planner, config.prompt_version_planner, planner_output.schema_version, plan_latency, _trace_input_summary(planner_input.recent_dialogue, user_turn), planner_output.status.value, planner_call, None))

    executor_input = build_executor_input(canonical_state, planner_output, user_turn, trace_meta, config.max_executor_recent_turns)
    exe_start = time.perf_counter()
    executor_call = _call_structured(client, config.model_executor, build_executor_messages(executor_prompt, executor_input), ExecutorOutput, "low", request_context, config.executor_store)
    executor_output = _executor_fallback(planner_output)
    if executor_call.source == StructuredCallSource.model and executor_call.parsed_json is not None:
        executor_output = ExecutorOutput.model_validate(executor_call.parsed_json)
    elif executor_call.source == StructuredCallSource.refusal:
        executor_output = _executor_fallback(planner_output, status=ExecutorStatus.refuse, refusal_reason=executor_call.refusal)
    exe_latency = int((time.perf_counter() - exe_start) * 1000)

    executor_output, enforcement_reason = _apply_executor_guardrails(executor_output, planner_output, user_turn, safety_policy)
    if executor_call.response is not None:
        update_thread_after_response(canonical_state.openai_thread, executor_call.response)
    logs.append(_build_trace_log(NodeName.executor, config.model_executor, config.prompt_version_executor, executor_output.schema_version, exe_latency, _trace_input_summary(executor_input.recent_dialogue_short, user_turn), executor_output.status.value if enforcement_reason is None else f"{executor_output.status.value}:{enforcement_reason}", executor_call, None))

    reply = executor_output.spoken_text
    add_message(state, role="assistant", content=reply)
    canonical_state.recent_messages.append(DialogueMessage(role="assistant", content=reply))
    canonical_state.recent_messages = _compact_recent(canonical_state.recent_messages, config.max_recent_messages)

    grades = _evaluate_stub(planner_output, executor_output) if config.feature_eval_hooks else EvalGrades(planner_coherence="disabled", executor_naturalness="disabled", planner_executor_agreement=True, safety_compliance=True)
    turn_trace = TurnTrace(
        turn_id=turn_id,
        timestamp_utc=now_iso,
        model_memory=config.model_memory,
        model_planner=config.model_planner,
        model_executor=config.model_executor,
        prompt_version_memory=config.prompt_version_memory,
        prompt_version_planner=config.prompt_version_planner,
        prompt_version_executor=config.prompt_version_executor,
        schema_version_memory=memory_patch.schema_version,
        schema_version_planner=planner_output.schema_version,
        schema_version_executor=executor_output.schema_version,
        sdk_compatibility=sdk_info,
        grades=grades,
        logs=logs,
    )

    canonical_state.trace = turn_trace.model_dump(mode="json")
    repo.save_state(state, canonical_state)
    if config.feature_traces:
        repo.append_trace(state, turn_trace)

    save_session_state(state)
    return reply, state
