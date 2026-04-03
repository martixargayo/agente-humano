from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Literal, Sequence, TypedDict

import openai
from pydantic import BaseModel, ConfigDict, ValidationError

from sessions.state import SessionState, add_message, save_session_state

from ..state.canonical_state import (
    CanonicalState,
    MemoryEpisodicItem,
    OpenAIThreadState,
    build_default_canonical_state,
)
from ..nodes.executor_node import (
    ExecutorInput,
    ExecutorOutput,
    ExecutorResponseLimits,
    ExecutorTaskContract,
)
from ..nodes.memory_node import DialogueMessage as MemoryDialogueMessage, MemoryInput, MemoryOutput, MemoryTaskContract, MemoryWorking as MemoryWorkingOutput, TraceMeta, UserTurn
from ..nodes.phase_classifier_node import (
    PhaseClassifierInput,
    PhaseClassifierOutput,
    build_phase_classifier_input,
    build_phase_classifier_messages,
)
from ..nodes.planner_node import (
    PhaseCard,
    PlannerContentPlan,
    PlannerInput,
    PlannerLimits,
    PlannerOutput,
    PlannerTaskContract,
    SelectedMemoryItem,
)
from ..state.shared_types import (
    NodeName,
    NegotiationPhase,
    SDKCompatibilityStatus,
    StructuredCallSource,
    ThreadMode,
)
from ..guards.builders import build_input_block_response
from .finish_button_rules import evaluate_finish_button_triggers
from ..guards.input import run_input_guardrails
from ..guards.models import InputGuardrailDecision, InputGuardrailResult, OutputGuardrailDecision, OutputGuardrailResult
from ..guards.output import run_output_guardrails
from ..guards.policy import build_guardrails_policy

from ..traces.builders import (
    build_executor_node_trace,
    build_memory_node_trace,
    build_phase_node_trace,
    build_planner_node_trace,
    excerpt,
)
from ..traces.constants import TRACE_VERSION
from ..traces.models import EvalGrades, PromptArtifacts, SDKCompatibilityInfo, StructuredCallResult, TurnTrace
from ..traces.context_meta import build_trace_context_meta
from ..forensics.provider_probe import get_turn_probe, record_provider_call, record_side_effect_hook, set_turn_id
from .context_errors import ImplicitContextForbiddenError
from .context_errors import InvalidConfigContextError, MissingTurnContextError, StatefulContextRequiredError

if TYPE_CHECKING:
    from .turn_context_validator import ValidatedTurnContext
from ..contexts import (
    PromptIOAdapter,
    PromptIOMappingError,
    load_prompt_io_adapter,
    read_bound_context_from_session,
    resolve_context_for_prompts_dir,
    resolve_default_negotiation_context,
    resolve_negotiation_context,
)

logger = logging.getLogger(__name__)

_tts_prefetch_hook: Callable[[str], None] | None = None


def set_tts_prefetch_hook(hook: Callable[[str], None] | None) -> None:
    global _tts_prefetch_hook
    _tts_prefetch_hook = hook

OPENAI_MIN_VERSION = "1.40.0"
PHASE_CLASSIFIER_INPUT_SCHEMA_VERSION = "phase_classifier_input.v1"
PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION = "phase_classifier.v1"
MAX_RECENT_PHASE_HISTORY = 5


# Centralized node threading contract:
# - memory/phase are parallel + stateless to avoid conversation locks.
# - planner/executor are stateless-sequential because their prompts are already fully structured.
NODE_THREADING_POLICIES: dict[str, str] = {
    "memory": "stateless_parallel",
    "phase_classifier": "stateless_parallel",
    # Planner input already includes recent_dialogue_short + memory_working + negotiation_state + selected_memory.
    # Keep it stateless to avoid duplicate context carry from Responses conversation history.
    "planner": "stateless_sequential",
    "executor": "stateless_sequential",
}


def _node_threading_policy(node_name: str) -> str:
    return NODE_THREADING_POLICIES.get(node_name, "stateful_sequential")


def _request_context_mode(context: dict[str, str]) -> str:
    if context.get("conversation"):
        return "conversation"
    if context.get("previous_response_id"):
        return "previous_response_id"
    return "stateless"


def _node_request_context(node_name: str, shared_context: dict[str, str]) -> tuple[dict[str, str], dict[str, object]]:
    policy = _node_threading_policy(node_name)
    if policy.startswith("stateless"):
        effective: dict[str, str] = {}
    else:
        effective = dict(shared_context)
    diagnostics = {
        "threading_policy": policy,
        "threading_mode_effective": _request_context_mode(effective),
        "request_context_has_conversation_id": bool(effective.get("conversation")),
        "request_context_has_previous_response_id": bool(effective.get("previous_response_id")),
    }
    logger.info(
        "node_threading_policy node=%s policy=%s mode=%s has_conversation=%s has_previous_response_id=%s",
        node_name,
        diagnostics["threading_policy"],
        diagnostics["threading_mode_effective"],
        diagnostics["request_context_has_conversation_id"],
        diagnostics["request_context_has_previous_response_id"],
    )
    return effective, diagnostics



class NegotiationTurnConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_key: str = "negotiation_canonical"
    context_id: str | None = None
    stateful: bool = False
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
    # Legacy compatibility flag. Guardrails v1 now use feature_input_guardrails/feature_output_guardrails/feature_moderation.
    feature_safety: bool = True
    feature_input_guardrails: bool = True
    feature_output_guardrails: bool = True
    feature_moderation: bool = True
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
    feature_input_guardrails: bool
    feature_output_guardrails: bool
    feature_moderation: bool
    feature_traces: bool
    feature_eval_hooks: bool
    enforce_sdk_compatibility: bool


BASE_DIR = Path(__file__).resolve().parent
LEGACY_PROMPTS_DIR = BASE_DIR.parent / "prompts"

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
    "feature_input_guardrails": True,
    "feature_output_guardrails": True,
    "feature_moderation": True,
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
        canonical_state.session.updated_at = datetime.now(timezone.utc).isoformat()
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


def build_negotiation_pipeline_config(*, context_id: str | None = None, stateful: bool = False) -> NegotiationTurnConfig:
    resolved_context = resolve_negotiation_context(context_id) if context_id else resolve_default_negotiation_context()
    return NegotiationTurnConfig(
        memory_key=NEGOTIATION_FLOW_DETAILS["memory_key"],
        context_id=resolved_context.context_id,
        stateful=stateful,
        prompts_dir=str(resolved_context.prompts_dir),
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
        feature_input_guardrails=NEGOTIATION_FLOW_DETAILS["feature_input_guardrails"],
        feature_output_guardrails=NEGOTIATION_FLOW_DETAILS["feature_output_guardrails"],
        feature_moderation=NEGOTIATION_FLOW_DETAILS["feature_moderation"],
        feature_traces=NEGOTIATION_FLOW_DETAILS["feature_traces"],
        feature_eval_hooks=NEGOTIATION_FLOW_DETAILS["feature_eval_hooks"],
        enforce_sdk_compatibility=NEGOTIATION_FLOW_DETAILS["enforce_sdk_compatibility"],
    )


def derive_config_context_id(config: NegotiationTurnConfig) -> str | None:
    explicit = (config.context_id or "").strip() or None
    from_prompts = resolve_context_for_prompts_dir(config.prompts_dir)
    prompts_context_id = from_prompts.context_id if from_prompts is not None else None
    if explicit is None:
        return prompts_context_id
    if prompts_context_id is None:
        return explicit
    if prompts_context_id != explicit:
        return None
    return explicit


def _default_canonical_state(session_state: SessionState | None = None, thread_mode: ThreadMode = ThreadMode.conversation) -> CanonicalState:
    session_id = session_state.session_id if session_state and session_state.session_id else "pending_session"
    user_id = session_state.user_id if session_state and session_state.user_id else None
    bound = read_bound_context_from_session(session_state) if session_state is not None else None
    context_id = bound.context_id if bound is not None else None
    return build_default_canonical_state(session_id=session_id, user_id=user_id, thread_mode=thread_mode, context_id=context_id)


# ==================================================
# A) Construcción de contexto
# ==================================================

def _build_user_turn(user_message: str, now_iso: str) -> UserTurn:
    normalized = " ".join(user_message.strip().split())
    return UserTurn(raw_text=user_message, normalized_text=normalized, modality="text", language="es", timestamp_iso=now_iso)


def _compact_recent(recent: Sequence[MemoryDialogueMessage], max_messages: int) -> List[MemoryDialogueMessage]:
    return list(recent[-max_messages:])




def _phase_classifier_card_fallback(path: Path, error: Exception | None = None) -> tuple[dict[str, object], str]:
    fallback_card = {
        "phase_classifier_card": {
            "purpose": "Fallback guidance for phase classification when prompt card file is unavailable.",
            "output_expectation": "Devuelve la fase dominante actual con criterio conservador y continuidad contextual.",
        }
    }
    source = f"fallback:{path}"
    if error is not None:
        source = f"{source} error={type(error).__name__}"
    return fallback_card, source


def _resolve_context_asset_path(
    prompts_dir: str,
    *,
    asset_name: Literal["phase_cards", "phase_classifier_card"],
) -> Path:
    prompts_path = Path(prompts_dir)
    resolved_context = resolve_context_for_prompts_dir(prompts_path)
    if resolved_context is not None:
        if asset_name == "phase_cards":
            return resolved_context.phase_cards_path
        return resolved_context.phase_classifier_card_path

    if prompts_path == LEGACY_PROMPTS_DIR:
        return LEGACY_PROMPTS_DIR / f"{asset_name}.json"

    return prompts_path / f"{asset_name}.json"


def _load_phase_classifier_card(prompts_dir: str) -> tuple[dict[str, object], str]:
    path = _resolve_context_asset_path(prompts_dir, asset_name="phase_classifier_card")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("phase_classifier_card_load_failed path=%s error=%s", path, exc)
        return _phase_classifier_card_fallback(path, exc)

    if not isinstance(raw, dict):
        logger.warning("phase_classifier_card_invalid_shape path=%s", path)
        return _phase_classifier_card_fallback(path)

    def _find_classifier_card(payload: object) -> dict[str, object] | None:
        if isinstance(payload, dict):
            for candidate_key in ("phase_classifier_card", "card", "phase_card", "classifier_card"):
                candidate = payload.get(candidate_key)
                if isinstance(candidate, dict):
                    return candidate
            for value in payload.values():
                found = _find_classifier_card(value)
                if found is not None:
                    return found
            if payload:
                return payload
        elif isinstance(payload, list):
            for item in payload:
                found = _find_classifier_card(item)
                if found is not None:
                    return found
        return None

    card = _find_classifier_card(raw)
    if isinstance(card, dict):
        return card, str(path)
    return _phase_classifier_card_fallback(path)


def _load_phase_cards(prompts_dir: str) -> dict[NegotiationPhase, PhaseCard]:
    path = _resolve_context_asset_path(prompts_dir, asset_name="phase_cards")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("phase_cards_load_failed path=%s error=%s", path, exc)
        raw = {}

    if isinstance(raw, dict):
        if isinstance(raw.get("phase_cards"), dict):
            raw = raw["phase_cards"]
        elif isinstance(raw.get("phases"), dict):
            raw = raw["phases"]
        elif isinstance(raw.get("cards"), dict):
            raw = raw["cards"]
        elif isinstance(raw.get("phases"), list):
            raw = {
                item.get("phase"): item
                for item in raw["phases"]
                if isinstance(item, dict) and isinstance(item.get("phase"), str)
            }

    def _find_phase_payload(payload: object, phase_name: str) -> dict[str, object] | None:
        if isinstance(payload, dict):
            direct = payload.get(phase_name)
            if isinstance(direct, dict):
                return direct
            for value in payload.values():
                found = _find_phase_payload(value, phase_name)
                if found is not None:
                    return found
        elif isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("phase") == phase_name:
                    return item
                found = _find_phase_payload(item, phase_name)
                if found is not None:
                    return found
        return None

    cards: dict[NegotiationPhase, PhaseCard] = {}
    for phase in NegotiationPhase:
        phase_raw = _find_phase_payload(raw, phase.value) or {}
        if not isinstance(phase_raw, dict):
            phase_raw = {}
        phase_payload = dict(phase_raw)
        phase_payload.setdefault("phase", phase.value)
        if not phase_payload.get("guidance"):
            phase_payload["guidance"] = f"Fallback guidance for phase {phase.value}."
        cards[phase] = PhaseCard.model_validate(phase_payload)
    return cards



def _recent_phase_history(canonical_state: CanonicalState) -> List[NegotiationPhase]:
    items: List[NegotiationPhase] = list(canonical_state.planner_state.recent_phase_history)
    if not items:
        if canonical_state.planner_state.previous_phase is not None:
            items.append(canonical_state.planner_state.previous_phase)
        if canonical_state.planner_state.current_phase is not None:
            items.append(canonical_state.planner_state.current_phase)
    return items[-MAX_RECENT_PHASE_HISTORY:]


def _select_phase_card(current_phase: NegotiationPhase, phase_cards: dict[NegotiationPhase, PhaseCard]) -> PhaseCard:
    return phase_cards[current_phase]


def build_phase_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta, prompts_dir: str) -> PhaseClassifierInput:
    short_recent = _compact_recent(recent_dialogue, 4)
    if short_recent and short_recent[-1].role == "user" and short_recent[-1].text == user_turn.normalized_text:
        short_recent = short_recent[:-1]

    phase_classifier_card, phase_classifier_card_source = _load_phase_classifier_card(prompts_dir)

    return build_phase_classifier_input(
        previous_phase=canonical_state.planner_state.current_phase,
        recent_phase_history=_recent_phase_history(canonical_state),
        phase_classifier_card=phase_classifier_card,
        phase_classifier_card_source=phase_classifier_card_source,
        recent_turns=short_recent,
        current_user_turn=user_turn,
        scene_state=canonical_state.scene_state,
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


def _select_memory_for_executor(canonical_state: CanonicalState, planner_output: PlannerOutput, max_items: int = 2) -> List[SelectedMemoryItem]:
    fallback = _select_memory(canonical_state, max_items=max_items)
    if not planner_output.memory_targets:
        return fallback

    planner_candidates = _select_memory(canonical_state)
    by_id = {item.memory_id: item for item in planner_candidates}

    selected_from_targets: List[SelectedMemoryItem] = []
    seen: set[str] = set()
    for target in planner_output.memory_targets:
        item = by_id.get(target)
        if item is None or item.memory_id in seen:
            continue
        selected_from_targets.append(item)
        seen.add(item.memory_id)

    return selected_from_targets or fallback


def build_memory_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta) -> MemoryInput:
    # /// episodic selection window remains provisional until memory retention policy is finalized.
    return MemoryInput(
        schema_version="memory_input.v1",
        task_contract=MemoryTaskContract(
            node_name="memory",
            objective="actualizar memoria episódica, memoria de trabajo y estado negociador vivo",
            completion_criteria=[
                "episodic_append contiene solo eventos nuevos, relevantes y no duplicados",
                "working_memory_new viene completo y factual",
                "negotiation_state refleja un snapshot operativo actualizado",
                "la salida cumple exactamente el schema MemoryOutput",
            ],
            output_schema_version="memory.v1",
        ),
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, 8),
        memory_working_current=canonical_state.memory_working,
        scene_state=canonical_state.scene_state,
        recent_memory_episodic_short=canonical_state.memory_episodic[-4:],
        trace_meta=trace_meta,
    )


def build_planner_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], user_turn: UserTurn, trace_meta: TraceMeta, prompts_dir: str) -> PlannerInput:
    current_phase = canonical_state.planner_state.current_phase or NegotiationPhase.clima_humano
    phase_card = _select_phase_card(current_phase, _load_phase_cards(prompts_dir))
    # current_turn_goal is tactical output of the previous planner step; keep it in state for traces,
    # but do not feed it as an anchor for the next planning cycle.
    planner_state_for_input = canonical_state.planner_state.model_copy(deep=True)
    planner_state_for_input.current_turn_goal = None
    # /// La selección de phase_card la hace código (lookup por fase), no el modelo planner.
    return PlannerInput(
        schema_version="planner_input.v1",
        task_contract=PlannerTaskContract(
            node_name="planner",
            objective="decidir el mejor plan táctico del siguiente turno",
            completion_criteria=[
                "el objetivo del turno es claro",
                "la decisión táctica es coherente con la fase actual",
                "el plan es compacto y ejecutable",
                "la salida cumple exactamente el schema PlannerOutput",
            ],
            output_schema_version="planner.v3",
        ),
        persona_policy=canonical_state.persona.policy,
        negotiation_brief=canonical_state.negotiation_brief,
        current_phase=current_phase,
        phase_card=phase_card,
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, 8),
        memory_working=canonical_state.memory_working,
        negotiation_state=canonical_state.negotiation_state,
        planner_state=planner_state_for_input,
        scene_state=canonical_state.scene_state,
        selected_memory=_select_memory(canonical_state),
        trace_meta=trace_meta,
    )


def build_executor_input(canonical_state: CanonicalState, recent_dialogue: Sequence[MemoryDialogueMessage], planner_output: PlannerOutput, user_turn: UserTurn, trace_meta: TraceMeta, max_recent_turns: int, prompts_dir: str) -> ExecutorInput:
    current_phase = canonical_state.planner_state.current_phase or NegotiationPhase.clima_humano
    phase_card = _select_phase_card(current_phase, _load_phase_cards(prompts_dir))
    return ExecutorInput(
        schema_version="executor_input.v1",
        task_contract=ExecutorTaskContract(
            node_name="executor",
            objective="producir la respuesta final orientada al usuario a partir de planner_output",
            completion_criteria=[
                "la respuesta es natural y humana",
                "permanece dentro de los límites del planner",
                "respeta response_limits",
                "la salida cumple exactamente el schema ExecutorOutput",
                "no replanifica ni altera la estrategia",
            ],
            output_schema_version="executor.v1",
        ),
        persona_expressive=canonical_state.persona.expressive,
        current_phase=current_phase,
        phase_card=phase_card,
        user_turn=user_turn,
        recent_dialogue_short=_compact_recent(recent_dialogue, max_recent_turns * 2),
        planner_output=planner_output,
        scene_state=canonical_state.scene_state,
        selected_memory_for_reference=_select_memory_for_executor(canonical_state, planner_output, max_items=2),
        response_limits=ExecutorResponseLimits(
            max_sentences=planner_output.limits.max_sentences,
            max_questions=planner_output.limits.max_questions,
            allow_topic_shift=planner_output.limits.allow_topic_shift,
            allow_personal_disclosure=planner_output.limits.allow_personal_disclosure,
        ),
        trace_meta=trace_meta,
    )


def build_memory_messages(memory_prompt: str, payload: MemoryInput) -> List[dict[str, str]]:
    return build_memory_messages_from_payload_json(memory_prompt, payload.model_dump_json())


def build_memory_messages_from_payload_json(memory_prompt: str, payload_json: str) -> List[dict[str, str]]:
    return [
        {"role": "developer", "content": memory_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `MemoryOutput`.\n\n<memory_input_json>\n"
            f"{payload_json}\n"
            "</memory_input_json>\n</task_input>",
        },
    ]


def build_planner_messages(planner_prompt: str, payload: PlannerInput) -> List[dict[str, str]]:
    return build_planner_messages_from_payload_json(planner_prompt, payload.model_dump_json())


def build_planner_messages_from_payload_json(planner_prompt: str, payload_json: str) -> List[dict[str, str]]:
    return [
        {"role": "developer", "content": planner_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `PlannerOutput`.\n\n<planner_input_json>\n"
            f"{payload_json}\n"
            "</planner_input_json>\n</task_input>",
        },
    ]


def build_phase_classifier_messages_payload(phase_classifier_prompt: str, payload: PhaseClassifierInput) -> List[dict[str, str]]:
    return build_phase_classifier_messages(phase_classifier_prompt, payload)


def build_phase_classifier_messages_from_payload_json(phase_classifier_prompt: str, payload_json: str) -> List[dict[str, str]]:
    return [
        {"role": "developer", "content": phase_classifier_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `PhaseClassifierOutput`.\n\n<phase_classifier_input_json>\n"
            f"{payload_json}\n"
            "</phase_classifier_input_json>\n</task_input>",
        },
    ]


def build_executor_messages(executor_prompt: str, payload: ExecutorInput) -> List[dict[str, str]]:
    return build_executor_messages_from_payload_json(executor_prompt, payload.model_dump_json())


def build_executor_messages_from_payload_json(executor_prompt: str, payload_json: str) -> List[dict[str, str]]:
    return [
        {"role": "developer", "content": executor_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `ExecutorOutput`.\n\n<executor_input_json>\n"
            f"{payload_json}\n"
            "</executor_input_json>\n</task_input>",
        },
    ]


def _adapt_payload_json_for_prompt(adapter: PromptIOAdapter, node: Literal["memory", "phase_classifier", "planner", "executor"], payload_json: str) -> str:
    try:
        payload_dict = json.loads(payload_json)
    except Exception:
        return payload_json
    if not isinstance(payload_dict, dict):
        return payload_json
    adapted = adapter.adapt_input_payload(node, payload_dict)
    return json.dumps(adapted, ensure_ascii=False, separators=(",", ":"))


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




def _hash_text(value: str | None) -> str | None:
    if value is None:
        return None
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FrozenPromptCall:
    payload_snapshot: BaseModel | dict[str, Any] | list[Any]
    payload_json: str
    messages: list[dict[str, str]]
    artifacts: PromptArtifacts


def freeze_prompt_artifacts(
    *,
    developer_prompt_text: str,
    payload: BaseModel | dict[str, Any] | list[Any],
    render_user_prompt: Callable[[str], str],
    model_target: str,
    prompt_version: str,
    input_schema_version: str,
    output_schema_version: str,
    threading_info: dict[str, object],
) -> FrozenPromptCall:
    if isinstance(payload, BaseModel):
        payload_snapshot = payload.model_copy(deep=True)
        payload_json = payload_snapshot.model_dump_json()
    else:
        payload_snapshot = deepcopy(payload)
        payload_json = json.dumps(payload_snapshot, ensure_ascii=False, separators=(",", ":"))

    user_prompt_rendered = render_user_prompt(payload_json)
    messages = [
        {"role": "developer", "content": developer_prompt_text},
        {"role": "user", "content": user_prompt_rendered},
    ]
    artifacts = PromptArtifacts(
        developer_prompt_text=developer_prompt_text,
        user_prompt_rendered=user_prompt_rendered,
        input_payload_json=payload_json,
        model_target=model_target,
        prompt_version=prompt_version,
        input_schema_version=input_schema_version,
        output_schema_version=output_schema_version,
        threading_policy=str(threading_info.get("threading_policy")) if threading_info.get("threading_policy") is not None else None,
        threading_mode_effective=str(threading_info.get("threading_mode_effective")) if threading_info.get("threading_mode_effective") is not None else None,
        developer_prompt_hash=_hash_text(developer_prompt_text),
        user_prompt_hash=_hash_text(user_prompt_rendered),
        payload_hash=_hash_text(payload_json),
        developer_prompt_chars=len(developer_prompt_text),
        user_prompt_chars=len(user_prompt_rendered),
        payload_chars=len(payload_json),
    )
    return FrozenPromptCall(payload_snapshot=payload_snapshot, payload_json=payload_json, messages=messages, artifacts=artifacts)


def _normalize_schema_for_strict_json_schema(schema: object) -> object:
    """Normalize JSON Schema so every object with properties has full required keys.

    OpenAI Structured Outputs strict mode requires each object to explicitly list
    every key from `properties` in `required`; optionality must be expressed with
    nullable types (e.g. anyOf[..., null]) instead of omitting keys from required.
    """

    if isinstance(schema, dict):
        normalized = {key: _normalize_schema_for_strict_json_schema(value) for key, value in schema.items()}
        properties = normalized.get("properties")
        if isinstance(properties, dict):
            normalized["required"] = list(properties.keys())
        return normalized
    if isinstance(schema, list):
        return [_normalize_schema_for_strict_json_schema(item) for item in schema]
    return schema


def _call_structured(
    client: openai.OpenAI | None,
    model: str,
    messages: List[dict[str, str]],
    node_name: Literal["memory", "phase_classifier", "planner", "executor"],
    prompt_io_adapter: PromptIOAdapter,
    response_model: type[BaseModel],
    reasoning_effort: str,
    request_context: dict[str, str],
    store: bool,
) -> StructuredCallResult:
    if client is None:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=None, exception_error="client_unavailable", response=None, source=StructuredCallSource.fallback, model_called=False, raw_output_text=None)

    schema = prompt_io_adapter.output_schema(node_name, response_model) or response_model.model_json_schema()
    kwargs = {
        "model": model,
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": response_model.__name__,
                "schema": _normalize_schema_for_strict_json_schema(schema),
                "strict": True,
            }
        },
        "reasoning": {"effort": reasoning_effort},
        "store": store,
        **request_context,
    }

    try:
        response = record_provider_call(
            call_subtype="responses.create",
            node_name=node_name,
            model=model,
            payload=kwargs,
            request_context=request_context,
            fn=lambda: client.responses.create(**kwargs),
        )
    except Exception as exc:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=None, exception_error=str(exc), response=None, source=StructuredCallSource.exception, model_called=True, raw_output_text=None)

    refusal = _extract_refusal_text(response)
    if refusal:
        return StructuredCallResult(parsed_json=None, refusal=refusal, parse_error=None, exception_error=None, response=response, source=StructuredCallSource.refusal, model_called=True, raw_output_text=getattr(response, "output_text", None))

    output_text = getattr(response, "output_text", "")
    try:
        parsed_json_raw = json.loads(output_text or "{}")
        if not isinstance(parsed_json_raw, dict):
            raise ValueError("structured_output_not_dict")
        parsed_json = prompt_io_adapter.normalize_output_payload(node_name, parsed_json_raw)
        response_model.model_validate(parsed_json)
    except Exception as exc:
        return StructuredCallResult(parsed_json=None, refusal=None, parse_error=str(exc), exception_error=None, response=response, source=StructuredCallSource.parse_error, model_called=True, raw_output_text=output_text)

    return StructuredCallResult(parsed_json=parsed_json, refusal=None, parse_error=None, exception_error=None, response=response, source=StructuredCallSource.model, model_called=True, raw_output_text=output_text)


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
        conversation = record_provider_call(
            call_subtype="conversations.create",
            node_name="conversation_bootstrap",
            model=None,
            payload={},
            request_context={},
            fn=lambda: client.conversations.create(),
        )
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
        [MemoryEpisodicItem(event_type=item.event_type, event_summary=item.event_summary, turn_id=item.turn_id) for item in output.episodic_append]
    )
    # refreshed each turn from memory output
    canonical_state.memory_working.current_topic = output.working_memory_new.current_topic
    canonical_state.memory_working.pending_question = output.working_memory_new.pending_question
    canonical_state.memory_working.last_turn_summary = output.working_memory_new.last_turn_summary
    canonical_state.negotiation_state = output.negotiation_state.model_copy(deep=True)


def apply_planner_output_to_state(canonical_state: CanonicalState, planner_output: PlannerOutput) -> None:
    canonical_state.planner_state.current_turn_goal = planner_output.turn_goal


def apply_phase_classifier_output_to_state(canonical_state: CanonicalState, phase_output: PhaseClassifierOutput) -> None:
    previous_phase = canonical_state.planner_state.current_phase
    canonical_state.planner_state.previous_phase = previous_phase
    canonical_state.planner_state.current_phase = phase_output.current_phase
    if previous_phase is not None and previous_phase != phase_output.current_phase:
        # Reset turn goal when the dominant phase changes to avoid stale tactical anchors
        # leaking into planner input on the next stage.
        canonical_state.planner_state.current_turn_goal = None
    history = list(canonical_state.planner_state.recent_phase_history)
    history.append(phase_output.current_phase)
    canonical_state.planner_state.recent_phase_history = history[-MAX_RECENT_PHASE_HISTORY:]
    # /// La lógica de mover tópicos entre current/previous phases depende del contrato final planner-memory y no se define aquí.


def apply_finish_button_state(canonical_state: CanonicalState) -> None:
    armed_prev = canonical_state.ui_state.finish_button_armed
    trigger_eval = evaluate_finish_button_triggers(canonical_state)
    canonical_state.ui_state.finish_button_armed = armed_prev or trigger_eval.should_arm


# ==================================================
# E) Guardarraíles
# ==================================================


def _default_input_guardrail_result() -> InputGuardrailResult:
    return InputGuardrailResult(decision=InputGuardrailDecision.allow)


def _default_output_guardrail_result(status: str) -> OutputGuardrailResult:
    return OutputGuardrailResult(
        decision=OutputGuardrailDecision.allow,
        status_before=status,
        status_after=status,
        planner_contract_signals={"planner_status": "unknown", "executor_status": status, "violations": []},
        enforcement_mode="observe_only",
        enforcement_action="none",
        output_changed=False,
    )


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


def _append_unique_reason(container: list[str], reason: str | None) -> None:
    if not reason:
        return
    value = reason.strip()
    if value and value not in container:
        container.append(value)


def _collect_last_refusals(logs: Sequence, executor_output: ExecutorOutput) -> list[str]:
    """Collect only real refusal signals (model refusals + final refusal/block outcomes)."""
    reasons: list[str] = []
    for log in logs:
        _append_unique_reason(reasons, getattr(log, "refusal_reason", None))
    if executor_output.status == "refuse":
        _append_unique_reason(reasons, executor_output.refusal_reason)
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
    memory_messages: list[dict[str, str]] | None = None,
    phase_messages: list[dict[str, str]] | None = None,
    memory_prompt: str | None = None,
    phase_classifier_prompt: str | None = None,
    memory_input: MemoryInput | None = None,
    phase_input: PhaseClassifierInput | None = None,
    memory_context_override: dict[str, str] | None = None,
    phase_context_override: dict[str, str] | None = None,
    memory_threading_override: dict[str, object] | None = None,
    phase_threading_override: dict[str, object] | None = None,
    prompt_io_adapter: PromptIOAdapter | None = None,
) -> tuple[StructuredCallResult, int, dict[str, object], StructuredCallResult, int, dict[str, object], dict[str, str]]:
    """Run memory+phase in parallel with explicit per-node threading isolation."""

    if memory_messages is None:
        if memory_prompt is None or memory_input is None:
            raise ValueError("memory_messages or (memory_prompt + memory_input) must be provided")
        memory_messages = build_memory_messages(memory_prompt, memory_input)
    if phase_messages is None:
        if phase_classifier_prompt is None or phase_input is None:
            raise ValueError("phase_messages or (phase_classifier_prompt + phase_input) must be provided")
        phase_messages = build_phase_classifier_messages_payload(phase_classifier_prompt, phase_input)

    if memory_context_override is not None and memory_threading_override is not None:
        memory_context, memory_threading = memory_context_override, memory_threading_override
    else:
        memory_context, memory_threading = _node_request_context("memory", request_context)

    if phase_context_override is not None and phase_threading_override is not None:
        phase_context, phase_threading = phase_context_override, phase_threading_override
    else:
        phase_context, phase_threading = _node_request_context("phase_classifier", request_context)

    adapter = prompt_io_adapter or PromptIOAdapter.identity()

    def _run_memory_call(ctx: dict[str, str]) -> tuple[StructuredCallResult, int]:
        mem_start = time.perf_counter()
        call = _call_structured(
            client,
            config.model_memory,
            memory_messages,
            "memory",
            adapter,
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
            phase_messages,
            "phase_classifier",
            adapter,
            PhaseClassifierOutput,
            "low",
            ctx,
            config.memory_store,
        )
        latency = int((time.perf_counter() - phase_start) * 1000)
        return call, latency

    with ThreadPoolExecutor(max_workers=2) as executor:
        mem_future = executor.submit(_run_memory_call, memory_context)
        phase_future = executor.submit(_run_phase_call, phase_context)
        mem_call, mem_latency = mem_future.result()
        phase_call, phase_latency = phase_future.result()

    # Memory/phase are intentionally stateless-isolated in parallel; do not update shared thread context from them.
    next_request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
    return mem_call, mem_latency, memory_threading, phase_call, phase_latency, phase_threading, next_request_context


def _memory_fallback(canonical_state: CanonicalState, turn_id: str) -> MemoryOutput:
    return MemoryOutput(
        schema_version="memory.v1",
        episodic_append=[],
        working_memory_new=MemoryWorkingOutput(
            current_topic=canonical_state.memory_working.current_topic,
            pending_question=canonical_state.memory_working.pending_question,
            last_turn_summary=canonical_state.memory_working.last_turn_summary or f"turn {turn_id}: sin cambios de memoria",
        ),
        negotiation_state=canonical_state.negotiation_state.model_copy(deep=True),
    )


def _phase_classifier_fallback(previous_phase: NegotiationPhase | None) -> PhaseClassifierOutput:
    return PhaseClassifierOutput(schema_version=PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION, current_phase=previous_phase or NegotiationPhase.clima_humano)


def _planner_fallback(status: Literal["clarify", "refuse"] = "clarify", refusal_reason: str | None = None) -> PlannerOutput:
    _ = refusal_reason
    decision = "ask" if status == "clarify" else "hold"
    turn_goal = "pedir dato mínimo para continuar" if status == "clarify" else "declinar bajo reglas vigentes"
    done = "aclaración_minima_emitida" if status == "clarify" else "negativa_emitida"
    return PlannerOutput(
        schema_version="planner.v3",
        status=status,
        turn_goal=turn_goal,
        decision=decision,
        content_plan=PlannerContentPlan(must_include=["movimiento táctico conservador"], must_avoid=["inventar hechos"]),
        limits=PlannerLimits(max_sentences=3, max_questions=1, allow_topic_shift=False, allow_personal_disclosure=False),
        memory_targets=[],
        done_criteria=[done],
    )


def _looks_like_greeting(text: str | None) -> bool:
    if not text:
        return False
    normalized = " ".join(text.strip().lower().split())
    return normalized in {"hola", "buenas", "buenos días", "buenas tardes", "buenas noches", "hey", "hello"}


def _executor_fallback(planner_output: PlannerOutput, status: str | None = None, refusal_reason: str | None = None, user_text: str | None = None) -> ExecutorOutput:
    resolved_status = status or ("refuse" if planner_output.status == "refuse" else "clarify" if planner_output.status == "clarify" else "deliver")
    if resolved_status == "refuse":
        text = "No puedo ayudar con esa solicitud."
    elif resolved_status == "clarify":
        text = "¿Me compartes un poco más de contexto para ayudarte mejor?"
    elif _looks_like_greeting(user_text):
        text = "¡Hola! ¿En qué te ayudo?"
    else:
        text = "Entendido. Sigamos con ello."
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

def run_negotiation_cognitive_turn(
    state: SessionState,
    user_message: str,
    config: NegotiationTurnConfig,
    *,
    validated_context: "ValidatedTurnContext | None" = None,
) -> tuple[str, SessionState]:
    if config.stateful and not (config.context_id or "").strip():
        raise ImplicitContextForbiddenError(message="stateful_runtime_requires_config_context")
    if config.stateful:
        if validated_context is None:
            raise MissingTurnContextError(message="stateful_runtime_requires_validated_context")
        if not validated_context.effective_context_id or not validated_context.config_context_id:
            raise StatefulContextRequiredError(message="validated_context_missing_required_ids")
        if validated_context.effective_context_id != config.context_id:
            raise InvalidConfigContextError(
                message="validated_effective_context_mismatch_config",
                expected=config.context_id,
                actual=validated_context.effective_context_id,
            )
        if validated_context.config_context_id != config.context_id:
            raise InvalidConfigContextError(
                message="validated_config_context_mismatch_config",
                expected=config.context_id,
                actual=validated_context.config_context_id,
            )
        resolved_for_prompts = resolve_context_for_prompts_dir(config.prompts_dir)
        if resolved_for_prompts is None or resolved_for_prompts.context_id != config.context_id:
            raise InvalidConfigContextError(
                message="runtime_prompts_context_mismatch_config",
                expected=config.context_id,
                actual=resolved_for_prompts.context_id if resolved_for_prompts is not None else None,
            )
    sdk_info = check_openai_sdk_compatibility(strict=config.enforce_sdk_compatibility)

    repo = StateRepository(memory_key=config.memory_key)
    canonical_state = repo.load_state(state, thread_mode=config.thread_mode_default)
    recent_dialogue = repo.load_recent_dialogue(state)

    turn_started_perf = time.perf_counter()
    turn_started_at = datetime.now(timezone.utc).isoformat()
    stage_timings_ms: dict[str, int] = {}
    turn_id = str(uuid.uuid4())
    now_iso = turn_started_at
    memory_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_memory, schema_version="memory_input.v1", model_target=config.model_memory)
    phase_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_phase_classifier, schema_version=PHASE_CLASSIFIER_INPUT_SCHEMA_VERSION, model_target=config.model_phase_classifier)
    planner_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_planner, schema_version="planner_input.v1", model_target=config.model_planner)
    executor_trace_meta = TraceMeta(turn_id=turn_id, prompt_version=config.prompt_version_executor, schema_version="executor_input.v1", model_target=config.model_executor)
    user_turn = _build_user_turn(user_message, now_iso)

    prompts_dir = Path(config.prompts_dir)
    resolved_context = resolve_context_for_prompts_dir(prompts_dir)
    try:
        prompt_io_adapter = load_prompt_io_adapter(resolved_context.prompt_io_mapping_path if resolved_context is not None else None)
    except PromptIOMappingError as exc:
        raise RuntimeError(f"prompt_io_mapping_invalid prompts_dir={prompts_dir} error={exc}") from exc

    memory_prompt = _read_text(prompts_dir / "summarizer_prompt.txt", "Identity: memory node\nOutput: MemoryOutput JSON estricto")
    phase_classifier_prompt = _read_text(prompts_dir / "phase_classifier_prompt.txt", "Clasifica la fase conversacional actual y devuelve SOLO current_phase en JSON estricto.")
    planner_prompt = _read_text(prompts_dir / "planner_prompt.txt", "[ROLE] planner\n[CONTRACT] return only PlannerOutput json\n[SUCCESS] strong intent, limits and safety")
    executor_prompt = _read_text(prompts_dir / "executor_prompt.txt", "[ROLE] executor\n[CONTRACT] return only ExecutorOutput json\n[SUCCESS] realize planner without replanning")

    thread_before = canonical_state.openai_thread.model_copy(deep=True)
    client = _build_client()
    policy = build_guardrails_policy(
        feature_input_guardrails=config.feature_input_guardrails,
        feature_output_guardrails=config.feature_output_guardrails,
        feature_moderation=config.feature_moderation,
    )

    input_guardrails_started = time.perf_counter()
    input_result = run_input_guardrails(user_text=user_turn.normalized_text, policy=policy, client=client)
    stage_timings_ms["input_guardrails"] = int((time.perf_counter() - input_guardrails_started) * 1000)
    output_result = _default_output_guardrail_result("not_executed")

    logs: list = []
    nodes: dict = {}
    planner_output = _planner_fallback()
    executor_output = _executor_fallback(planner_output, status="clarify")
    executor_output_before_guardrail = executor_output.model_copy(deep=True)

    # v1 semantics: soft_restrict is a risk marker only; it does not alter normal node execution yet.
    if input_result.decision in {InputGuardrailDecision.allow, InputGuardrailDecision.soft_restrict}:
        add_message(state, role="user", content=user_message)
        recent_dialogue.append(MemoryDialogueMessage(role="user", text=user_turn.normalized_text))
        recent_dialogue = _compact_recent(recent_dialogue, config.max_recent_messages)

    if input_result.decision == InputGuardrailDecision.block:
        reply = build_input_block_response()
        executor_output = _executor_fallback(planner_output, status="refuse", refusal_reason="input_guardrail_block", user_text=user_turn.normalized_text)
        executor_output_before_guardrail = executor_output.model_copy(deep=True)
        executor_output = executor_output.model_copy(update={"spoken_text": reply})
    else:
        request_context_started = time.perf_counter()
        request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
        stage_timings_ms["request_context_initial"] = int((time.perf_counter() - request_context_started) * 1000)

        memory_input = build_memory_input(canonical_state, recent_dialogue, user_turn, memory_trace_meta)
        phase_input = build_phase_input(canonical_state, recent_dialogue, user_turn, phase_trace_meta, str(prompts_dir))
        memory_context, memory_threading = _node_request_context("memory", request_context)
        memory_frozen = freeze_prompt_artifacts(
            developer_prompt_text=memory_prompt,
            payload=memory_input,
            render_user_prompt=lambda payload_json: build_memory_messages_from_payload_json(
                memory_prompt,
                _adapt_payload_json_for_prompt(prompt_io_adapter, "memory", payload_json),
            )[1]["content"],
            model_target=memory_trace_meta.model_target,
            prompt_version=memory_trace_meta.prompt_version,
            input_schema_version=memory_input.schema_version,
            output_schema_version="memory.v1",
            threading_info=memory_threading,
        )
        phase_context, phase_threading = _node_request_context("phase_classifier", request_context)
        phase_frozen = freeze_prompt_artifacts(
            developer_prompt_text=phase_classifier_prompt,
            payload=phase_input,
            render_user_prompt=lambda payload_json: build_phase_classifier_messages_from_payload_json(
                phase_classifier_prompt,
                _adapt_payload_json_for_prompt(prompt_io_adapter, "phase_classifier", payload_json),
            )[1]["content"],
            model_target=phase_trace_meta.model_target,
            prompt_version=phase_trace_meta.prompt_version,
            input_schema_version=phase_input.schema_version,
            output_schema_version=PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION,
            threading_info=phase_threading,
        )
        memory_phase_started = time.perf_counter()
        memory_phase_result = _execute_memory_and_phase(
            client=client,
            config=config,
            canonical_state=canonical_state,
            request_context=request_context,
            memory_messages=memory_frozen.messages,
            phase_messages=phase_frozen.messages,
            memory_input=memory_input,
            phase_input=phase_input,
            memory_context_override=memory_context,
            phase_context_override=phase_context,
            memory_threading_override=memory_threading,
            phase_threading_override=phase_threading,
            prompt_io_adapter=prompt_io_adapter,
        )
        if len(memory_phase_result) == 7:
            mem_call, mem_latency, mem_threading, phase_call, phase_latency, phase_threading, request_context = memory_phase_result
        else:
            mem_call, mem_latency, phase_call, phase_latency, request_context = memory_phase_result
            mem_threading = _node_request_context("memory", request_context)[1]
            phase_threading = _node_request_context("phase_classifier", request_context)[1]
        stage_timings_ms["memory_phase_parallel_wall"] = int((time.perf_counter() - memory_phase_started) * 1000)
        stage_timings_ms["memory_call"] = mem_latency
        stage_timings_ms["phase_classifier_call"] = phase_latency

        memory_patch = _resolve_memory_call_result(canonical_state, turn_id, mem_call)
        phase_output = _resolve_phase_call_result(canonical_state, phase_call)
        apply_memory_output_to_state(canonical_state, memory_patch)
        apply_phase_classifier_output_to_state(canonical_state, phase_output)
        apply_finish_button_state(canonical_state)
        logs.append(build_memory_node_trace(memory_frozen.payload_snapshot, memory_patch, mem_call, mem_latency, "applied", mem_threading, memory_frozen.artifacts))
        logs.append(build_phase_node_trace(phase_frozen.payload_snapshot, phase_output, phase_call, phase_latency, phase_threading, phase_frozen.artifacts))

        planner_input = build_planner_input(canonical_state, recent_dialogue, user_turn, planner_trace_meta, config.prompts_dir)
        planner_request_context, planner_threading = _node_request_context("planner", request_context)
        planner_frozen = freeze_prompt_artifacts(
            developer_prompt_text=planner_prompt,
            payload=planner_input,
            render_user_prompt=lambda payload_json: build_planner_messages_from_payload_json(
                planner_prompt,
                _adapt_payload_json_for_prompt(prompt_io_adapter, "planner", payload_json),
            )[1]["content"],
            model_target=planner_trace_meta.model_target,
            prompt_version=planner_trace_meta.prompt_version,
            input_schema_version=planner_input.schema_version,
            output_schema_version="planner.v3",
            threading_info=planner_threading,
        )
        plan_start = time.perf_counter()
        planner_call = _call_structured(
            client,
            config.model_planner,
            planner_frozen.messages,
            "planner",
            prompt_io_adapter,
            PlannerOutput,
            config.reasoning_effort_planner,
            planner_request_context,
            config.planner_store,
        )
        planner_output = _planner_fallback()
        if planner_call.source == StructuredCallSource.model and planner_call.parsed_json is not None:
            planner_output = PlannerOutput.model_validate(planner_call.parsed_json)
        elif planner_call.source == StructuredCallSource.refusal:
            planner_output = _planner_fallback(status="refuse", refusal_reason=planner_call.refusal)
        plan_latency = int((time.perf_counter() - plan_start) * 1000)
        stage_timings_ms["planner_call"] = plan_latency

        apply_planner_output_to_state(canonical_state, planner_output)
        if planner_call.response is not None:
            update_thread_after_response(canonical_state.openai_thread, planner_call.response)
        request_context_after_planner_started = time.perf_counter()
        request_context = refresh_request_context(client, canonical_state, config.thread_mode_default)
        stage_timings_ms["request_context_after_planner"] = int((time.perf_counter() - request_context_after_planner_started) * 1000)
        logs.append(build_planner_node_trace(planner_frozen.payload_snapshot, planner_output, planner_call, plan_latency, planner_threading, planner_frozen.artifacts))

        executor_input = build_executor_input(canonical_state, recent_dialogue, planner_output, user_turn, executor_trace_meta, config.max_executor_recent_turns, config.prompts_dir)
        executor_request_context, executor_threading = _node_request_context("executor", request_context)
        executor_frozen = freeze_prompt_artifacts(
            developer_prompt_text=executor_prompt,
            payload=executor_input,
            render_user_prompt=lambda payload_json: build_executor_messages_from_payload_json(
                executor_prompt,
                _adapt_payload_json_for_prompt(prompt_io_adapter, "executor", payload_json),
            )[1]["content"],
            model_target=executor_trace_meta.model_target,
            prompt_version=executor_trace_meta.prompt_version,
            input_schema_version=executor_input.schema_version,
            output_schema_version="executor.v1",
            threading_info=executor_threading,
        )
        exe_start = time.perf_counter()
        executor_call = _call_structured(
            client,
            config.model_executor,
            executor_frozen.messages,
            "executor",
            prompt_io_adapter,
            ExecutorOutput,
            "low",
            executor_request_context,
            config.executor_store,
        )
        executor_output = _executor_fallback(planner_output, user_text=user_turn.normalized_text)
        if executor_call.source == StructuredCallSource.model and executor_call.parsed_json is not None:
            executor_output = ExecutorOutput.model_validate(executor_call.parsed_json)
        elif executor_call.source == StructuredCallSource.refusal:
            executor_output = _executor_fallback(planner_output, status="refuse", refusal_reason=executor_call.refusal, user_text=user_turn.normalized_text)
        exe_latency = int((time.perf_counter() - exe_start) * 1000)
        stage_timings_ms["executor_call"] = exe_latency

        if executor_call.response is not None:
            update_thread_after_response(canonical_state.openai_thread, executor_call.response)

        executor_output_before_guardrail = executor_output.model_copy(deep=True)
        output_guardrails_started = time.perf_counter()
        executor_output, output_result = run_output_guardrails(
            executor_output=executor_output,
            planner_output=planner_output,
            user_turn=user_turn,
            policy=policy,
            client=client,
        )
        stage_timings_ms["output_guardrails"] = int((time.perf_counter() - output_guardrails_started) * 1000)
        logs.append(build_executor_node_trace(executor_frozen.payload_snapshot, executor_output_before_guardrail, executor_output, executor_call, exe_latency, executor_output.status, guardrail_applied=output_result.rewrite_applied or output_result.status_before != output_result.status_after, status_before_guardrail=output_result.status_before, status_after_guardrail=output_result.status_after, threading_info=executor_threading, prompt_artifacts=executor_frozen.artifacts))
        nodes = {log.node.value: log for log in logs}
        reply = executor_output.spoken_text

    if _tts_prefetch_hook is not None:
        hook_error: str | None = None
        try:
            _tts_prefetch_hook(reply)
        except Exception as exc:
            hook_error = str(exc)
            logger.warning("tts_prefetch_hook_error=%s", exc)
        finally:
            record_side_effect_hook(hook_name="tts_prefetch_hook", payload={"reply_chars": len(reply or "")}, error=hook_error)

    add_message(state, role="assistant", content=reply)
    recent_dialogue.append(MemoryDialogueMessage(role="assistant", text=reply))
    recent_dialogue = _compact_recent(recent_dialogue, config.max_recent_messages)

    turn_finished_at = datetime.now(timezone.utc).isoformat()
    total_latency_ms = int((time.perf_counter() - turn_started_perf) * 1000)
    stage_timings_ms["total_turn"] = total_latency_ms
    grades = _evaluate_stub(planner_output, executor_output) if config.feature_eval_hooks else EvalGrades(planner_coherence="disabled", executor_naturalness="disabled", planner_executor_agreement=True, safety_compliance=True)

    combined_guardrail_reasons = sorted(set(input_result.reasons + output_result.reasons))
    output_triggered = bool(output_result.reasons)
    guardrails_triggered = input_result.decision != InputGuardrailDecision.allow or output_triggered

    trace_context_meta = build_trace_context_meta(state=state, validated_context=validated_context)

    set_turn_id(turn_id)
    turn_probe = get_turn_probe()
    executor_log = next((log for log in logs if log.node_name == "executor"), None)
    if executor_log is not None and executor_log.final_output_source == "post_guardrail_output":
        final_output_origin = "guardrail_rewrite" if output_result.rewrite_applied else "guardrail_status_adjustment"
    elif executor_log is not None and executor_log.final_output_source == "fallback_output":
        final_output_origin = "executor_fallback"
    elif executor_log is not None and executor_log.final_output_source == "validated_output":
        final_output_origin = "model"
    else:
        final_output_origin = "unknown"

    turn_trace = TurnTrace(
        trace_version=TRACE_VERSION,
        turn_id=turn_id,
        timestamp_utc=now_iso,
        turn_started_at=turn_started_at,
        turn_finished_at=turn_finished_at,
        total_latency_ms=total_latency_ms,
        session_id=canonical_state.session.session_id,
        user_id=canonical_state.session.user_id,
        avatar_id=canonical_state.session.avatar_id,
        thread_mode=canonical_state.openai_thread.thread_mode,
        conversation_id_before=thread_before.conversation_id,
        conversation_id_after=canonical_state.openai_thread.conversation_id,
        previous_response_id_before=thread_before.previous_response_id,
        previous_response_id_after=canonical_state.openai_thread.previous_response_id,
        user_turn=user_turn,
        final_reply_text=reply,
        final_reply_excerpt=excerpt(reply) or "",
        final_status=executor_output.status,
        assistant_turn_emitted=True,
        executor_reply_text_before_guardrail=executor_output_before_guardrail.spoken_text,
        executor_status_before_guardrail=executor_output_before_guardrail.status,
        executor_reply_changed_by_guardrail=executor_output_before_guardrail.spoken_text != reply or executor_output_before_guardrail.status != executor_output.status,
        final_output_source=final_output_origin,
        final_output_origin=final_output_origin,
        guardrails_triggered=guardrails_triggered,
        guardrail_reasons=combined_guardrail_reasons,
        guardrail_rewrite_applied=output_result.rewrite_applied,
        guardrail_status_before=output_result.status_before,
        guardrail_status_after=output_result.status_after,
        input_guardrail_decision=input_result.decision.value,
        input_guardrail_reasons=input_result.reasons,
        input_guardrail_triggered=input_result.decision != InputGuardrailDecision.allow,
        input_moderation_used=input_result.moderation_used,
        input_moderation_flags=input_result.moderation_flags,
        output_guardrail_decision=output_result.decision.value,
        output_guardrail_reasons=output_result.reasons,
        output_guardrail_triggered=output_triggered,
        output_guardrail_rewrite_applied=output_result.rewrite_applied,
        output_guardrail_enforcement_mode=output_result.enforcement_mode,
        output_guardrail_enforcement_action=output_result.enforcement_action,
        output_guardrail_observed_not_applied_rules=output_result.observed_not_applied_rules,
        output_guardrail_enforced_rules=output_result.enforced_rules,
        output_guardrail_output_changed=output_result.output_changed,
        output_guardrail_status_before=output_result.status_before,
        output_guardrail_status_after=output_result.status_after,
        output_moderation_used=output_result.moderation_used,
        output_moderation_flags=output_result.moderation_flags,
        model_memory=config.model_memory,
        model_phase_classifier=config.model_phase_classifier,
        model_planner=config.model_planner,
        model_executor=config.model_executor,
        prompt_version_memory=config.prompt_version_memory,
        prompt_version_phase_classifier=config.prompt_version_phase_classifier,
        prompt_version_planner=config.prompt_version_planner,
        prompt_version_executor=config.prompt_version_executor,
        schema_version_memory="memory.v1",
        schema_version_phase_classifier=PHASE_CLASSIFIER_OUTPUT_SCHEMA_VERSION,
        schema_version_planner=planner_output.schema_version,
        schema_version_executor=executor_output.schema_version,
        sdk_compatibility=sdk_info,
        grades=grades,
        context_meta=trace_context_meta,
        logs=logs,
        nodes=nodes,
        provider_calls=[event.__dict__ for event in (turn_probe.provider_calls if turn_probe is not None else [])],
        side_effect_hooks=(turn_probe.side_effect_hooks if turn_probe is not None else []),
        stage_timings_ms=stage_timings_ms,
    )

    canonical_state.trace.turn_id = turn_trace.turn_id
    canonical_state.trace.last_node_statuses = {log.node.value: log.status for log in logs}
    canonical_state.trace.last_fallbacks = [log.node.value for log in logs if log.source != StructuredCallSource.model]
    canonical_state.trace.last_refusals = _collect_last_refusals(logs, executor_output)
    repo.save_state(state, canonical_state)
    repo.save_recent_dialogue(state, recent_dialogue)
    if config.feature_traces:
        repo.append_trace(state, turn_trace)

    save_session_state(state)
    return reply, state
