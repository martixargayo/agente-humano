from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import openai
from pydantic import ValidationError

from sessions.state import SessionState, add_message, save_session_state

from ..contexts import (
    load_prompt_io_adapter,
    read_bound_conversacion_simple_context_from_session,
    resolve_conversacion_simple_context_for_prompts_dir,
)
from ..nodes import BrainInput, BrainOutput, BrainTaskContract, DialogueMessage, TraceMeta, UserTurn
from ..memory import (
    run_memory_maintenance_best_effort,
    schedule_memory_maintenance,
    should_schedule_compaction,
    trim_recent_dialogue,
)
from ..state import (
    ConversationSimpleCanonicalState,
    ConversationSimpleMemoryEpisodicItem,
    build_default_conversation_simple_canonical_state,
)
from ..traces import ConversationSimpleTurnTrace, build_brain_node_trace
from .flow_config import ConversationSimpleTurnConfig
from negociacion.orchestration.turn_execution_context import TurnExecutionContext


def _compact_recent(recent: list[DialogueMessage], max_messages: int) -> list[DialogueMessage]:
    return list(recent[-max_messages:])


def _build_user_turn(user_message: str, now_iso: str) -> UserTurn:
    normalized = " ".join(user_message.strip().split())
    return UserTurn(raw_text=user_message, normalized_text=normalized, modality="text", language="es", timestamp_iso=now_iso)


@dataclass
class ConversationSimpleStateRepository:
    memory_key: str
    recent_dialogue_key: str
    traces_key: str

    def load_state(self, session_state: SessionState, config: ConversationSimpleTurnConfig) -> ConversationSimpleCanonicalState:
        raw = session_state.world_state.get(self.memory_key, {}) if isinstance(session_state.world_state, dict) else {}
        if isinstance(raw, dict):
            try:
                return ConversationSimpleCanonicalState.model_validate(raw)
            except ValidationError:
                pass
        return build_default_conversation_simple_canonical_state(
            session_id=session_state.session_id,
            user_id=session_state.user_id,
            thread_mode=config_thread_mode_default(),
            context_id=config.context_id,
        )

    def save_state(self, session_state: SessionState, canonical_state: ConversationSimpleCanonicalState) -> None:
        canonical_state.session.updated_at = datetime.now(timezone.utc).isoformat()
        session_state.world_state[self.memory_key] = canonical_state.model_dump(mode="json")

    def load_recent_dialogue(self, session_state: SessionState) -> list[DialogueMessage]:
        raw = session_state.world_state.get(self.recent_dialogue_key, []) if isinstance(session_state.world_state, dict) else []
        if not isinstance(raw, list):
            return []
        result: list[DialogueMessage] = []
        for item in raw:
            if isinstance(item, dict):
                try:
                    result.append(DialogueMessage.model_validate(item))
                except ValidationError:
                    continue
        return result

    def save_recent_dialogue(self, session_state: SessionState, recent_dialogue: list[DialogueMessage]) -> None:
        session_state.world_state[self.recent_dialogue_key] = [item.model_dump(mode="json") for item in recent_dialogue]

    def append_trace(self, session_state: SessionState, trace: ConversationSimpleTurnTrace) -> None:
        traces = session_state.world_state.setdefault(self.traces_key, [])
        if not isinstance(traces, list):
            traces = []
            session_state.world_state[self.traces_key] = traces
        traces.append(trace.model_dump(mode="json"))


def config_thread_mode_default():
    from negociacion.state.shared_types import ThreadMode

    return ThreadMode.conversation


def build_brain_input(
    *,
    canonical_state: ConversationSimpleCanonicalState,
    recent_dialogue: list[DialogueMessage],
    user_turn: UserTurn,
    trace_meta: TraceMeta,
) -> BrainInput:
    return BrainInput(
        schema_version="brain_input.v1",
        task_contract=BrainTaskContract(
            node_name="brain",
            objective="resolver el turno completo en una sola llamada",
            completion_criteria=[
                "devuelve respuesta final y patch de estado",
                "actualiza memoria de trabajo de forma factual",
                "cumple schema BrainOutput",
            ],
            output_schema_version="brain.v1",
        ),
        persona=canonical_state.persona,
        conversation_brief=canonical_state.conversation_brief,
        conversation_state=canonical_state.conversation_state,
        memory_working=canonical_state.memory_working,
        recent_dialogue_short=_compact_recent(recent_dialogue, 8),
        user_turn=user_turn,
        trace_meta=trace_meta,
    )


def build_brain_messages(brain_prompt: str, payload: BrainInput) -> list[dict[str, str]]:
    return [
        {"role": "developer", "content": brain_prompt},
        {
            "role": "user",
            "content": "<task_input>\nDevuelve solo JSON válido para `BrainOutput`.\n\n<brain_input_json>\n"
            f"{payload.model_dump_json()}\n"
            "</brain_input_json>\n</task_input>",
        },
    ]


def _build_client() -> openai.OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return openai.OpenAI()
    except Exception:
        return None


@dataclass
class StructuredBrainCall:
    source: Literal["model", "fallback"]
    parsed_json: dict | None
    response: object | None
    response_id: str | None = None


def _extract_output_text(response: object) -> str | None:
    output = getattr(response, "output_text", None)
    if isinstance(output, str) and output.strip():
        return output
    return None


def _extract_response_id(response: object) -> str | None:
    value = getattr(response, "id", None)
    return value if isinstance(value, str) and value.strip() else None


def _call_brain_structured(
    *,
    client: openai.OpenAI | None,
    model: str,
    messages: list[dict[str, str]],
) -> StructuredBrainCall:
    if client is None:
        return StructuredBrainCall(source="fallback", parsed_json=None, response=None)
    response = client.responses.create(model=model, input=messages, reasoning={"effort": "low"})
    text = _extract_output_text(response)
    response_id = _extract_response_id(response)
    if not text:
        return StructuredBrainCall(source="fallback", parsed_json=None, response=response, response_id=response_id)
    try:
        payload = json.loads(text)
    except Exception:
        return StructuredBrainCall(source="fallback", parsed_json=None, response=response, response_id=response_id)
    return StructuredBrainCall(
        source="model",
        parsed_json=payload if isinstance(payload, dict) else None,
        response=response,
        response_id=response_id,
    )


def _brain_fallback() -> BrainOutput:
    return BrainOutput(
        schema_version="brain.v1",
        status="clarify",
        assistant_response={"text": "¿Me compartes un poco más de contexto para ayudarte mejor?"},
        state_patch={
            "conversation_state": {"phase": None, "status": "active", "current_turn_goal": "pedir aclaración mínima"},
            "memory_working": {"current_topic": None, "pending_question": None, "last_turn_summary": "aclaración solicitada"},
            "memory_episodic_append": [],
        },
    )


def _normalize_reply_text(reply: str) -> str:
    normalized = " ".join(reply.strip().split())
    if not normalized:
        raise RuntimeError("conversacion_simple_invalid_assistant_response_text")
    return normalized


def _coerce_legacy_brain_output_payload(
    *,
    payload: dict[str, object],
    canonical_state: ConversationSimpleCanonicalState,
) -> dict[str, object]:
    normalized = dict(payload)
    if "schema_version" not in normalized:
        normalized["schema_version"] = "brain.v1"
    if "status" not in normalized:
        normalized["status"] = "deliver"
    if "assistant_response" not in normalized and isinstance(normalized.get("response_text"), str):
        normalized["assistant_response"] = {"text": normalized["response_text"]}
    normalized.pop("response_text", None)
    if "state_patch" not in normalized:
        normalized["state_patch"] = {
            "conversation_state": canonical_state.conversation_state.model_dump(mode="json"),
            "memory_working": canonical_state.memory_working.model_dump(mode="json"),
            "memory_episodic_append": [],
        }
    return normalized


def _parse_brain_output_strict(
    *,
    payload: dict | None,
    allow_fallback: bool,
    canonical_state: ConversationSimpleCanonicalState,
) -> BrainOutput:
    if payload is None:
        if allow_fallback:
            return _brain_fallback()
        raise RuntimeError("conversacion_simple_brain_output_missing_json")
    payload = _coerce_legacy_brain_output_payload(payload=payload, canonical_state=canonical_state)
    try:
        output = BrainOutput.model_validate(payload)
    except ValidationError as exc:
        if allow_fallback:
            return _brain_fallback()
        raise RuntimeError("conversacion_simple_brain_output_validation_error") from exc
    output.assistant_response.text = _normalize_reply_text(output.assistant_response.text)
    return output


def apply_brain_output_to_state(*, canonical_state: ConversationSimpleCanonicalState, brain_output: BrainOutput, turn_id: str) -> None:
    canonical_state.conversation_state = brain_output.state_patch.conversation_state.model_copy(deep=True)
    canonical_state.memory_working = brain_output.state_patch.memory_working.model_copy(deep=True)
    append_items: list[ConversationSimpleMemoryEpisodicItem] = []
    for item in brain_output.state_patch.memory_episodic_append:
        event_type = item.get("event_type")
        event_summary = item.get("event_summary")
        if not isinstance(event_type, str) or not isinstance(event_summary, str):
            continue
        if event_type not in {"important_fact", "intent", "constraint", "commitment"}:
            continue
        append_items.append(
            ConversationSimpleMemoryEpisodicItem(event_type=event_type, event_summary=event_summary, turn_id=item.get("turn_id") or turn_id)
        )
    canonical_state.memory_episodic.extend(append_items)
    canonical_state.trace.turn_id = turn_id
    canonical_state.trace.last_status = brain_output.status


def _validate_turn_context(*, state: SessionState, config: ConversationSimpleTurnConfig, turn_context: TurnExecutionContext | None) -> str:
    if config.stateful and turn_context is None:
        raise RuntimeError("conversacion_simple_turn_context_required_for_stateful")
    if turn_context is None or not turn_context.effective_context_id:
        raise RuntimeError("conversacion_simple_effective_context_required")
    effective_context_id = turn_context.effective_context_id
    bound = read_bound_conversacion_simple_context_from_session(state)
    if bound is None or bound.context_id != effective_context_id:
        raise RuntimeError("conversacion_simple_session_context_mismatch")
    if config.context_id != effective_context_id:
        raise RuntimeError("conversacion_simple_config_context_mismatch")
    resolved = resolve_conversacion_simple_context_for_prompts_dir(config.prompts_dir)
    if resolved is None or resolved.context_id != effective_context_id:
        raise RuntimeError("conversacion_simple_prompts_context_mismatch")
    return effective_context_id


def run_conversacion_simple_turn(
    *,
    state: SessionState,
    user_message: str,
    config: ConversationSimpleTurnConfig,
    turn_context: TurnExecutionContext | None,
) -> tuple[str, SessionState, dict[str, object]]:
    effective_context_id = _validate_turn_context(state=state, config=config, turn_context=turn_context)
    repo = ConversationSimpleStateRepository(
        memory_key=config.memory_key,
        recent_dialogue_key=config.recent_dialogue_key,
        traces_key=config.traces_key,
    )
    canonical_state = repo.load_state(state, config)
    recent_dialogue = repo.load_recent_dialogue(state)
    memory_obs: dict[str, object] = {}

    turn_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    user_turn = _build_user_turn(user_message, now_iso)
    trace_meta = TraceMeta(turn_id=turn_id, prompt_version="brain_v1", schema_version="brain_input.v1", model_target="gpt-5-nano")

    prompts_dir = Path(config.prompts_dir)
    prompt_text = (prompts_dir / "brain_prompt.txt").read_text(encoding="utf-8").strip()
    _ = load_prompt_io_adapter(None)
    client = _build_client()
    llm_call_attempted = client is not None

    add_message(state, role="user", content=user_message)
    recent_dialogue.append(DialogueMessage(role="user", text=user_turn.normalized_text))
    recent_dialogue, recent_metrics_user = trim_recent_dialogue(
        recent_dialogue=recent_dialogue,
        max_messages=config.max_recent_dialogue_messages,
    )
    memory_obs.update(recent_metrics_user)

    brain_input = build_brain_input(canonical_state=canonical_state, recent_dialogue=recent_dialogue, user_turn=user_turn, trace_meta=trace_meta)
    brain_messages = build_brain_messages(prompt_text, brain_input)

    started = time.perf_counter()
    call = _call_brain_structured(client=client, model=trace_meta.model_target, messages=brain_messages)
    brain_output = _parse_brain_output_strict(
        payload=call.parsed_json,
        allow_fallback=call.source != "model",
        canonical_state=canonical_state,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    # Apply deterministic patch
    apply_brain_output_to_state(canonical_state=canonical_state, brain_output=brain_output, turn_id=turn_id)

    reply = _normalize_reply_text(brain_output.assistant_response.text)
    add_message(state, role="assistant", content=reply)
    recent_dialogue.append(DialogueMessage(role="assistant", text=reply))
    recent_dialogue, recent_metrics_assistant = trim_recent_dialogue(
        recent_dialogue=recent_dialogue,
        max_messages=config.max_recent_dialogue_messages,
    )
    memory_obs.update(recent_metrics_assistant)

    schedule, schedule_reason = should_schedule_compaction(
        canonical_state=canonical_state,
        episodic_trigger_count=config.episodic_compaction_trigger_count,
        episodic_trigger_chars=config.episodic_compaction_trigger_chars,
    )
    if schedule:
        schedule_memory_maintenance(
            canonical_state=canonical_state,
            reason=schedule_reason,
            retry_limit=config.maintenance_retry_limit,
        )
    maintenance_obs = run_memory_maintenance_best_effort(
        canonical_state=canonical_state,
        high_resolution_limit=config.max_episodic_high_resolution_items,
        compacted_summary_max_chars=config.compacted_summary_max_chars,
        simulate_failure=config.maintenance_force_failure,
    )
    memory_obs.update(maintenance_obs)

    node_trace = build_brain_node_trace(
        latency_ms=latency_ms,
        status=brain_output.status,
        model_called=call.source == "model",
        recent_dialogue_count=len(brain_input.recent_dialogue_short),
        episodic_append_count=len(brain_output.state_patch.memory_episodic_append),
    )

    turn_trace = ConversationSimpleTurnTrace(
        turn_id=turn_id,
        timestamp_utc=now_iso,
        session_id=state.session_id,
        user_id=state.user_id,
        previous_response_id_after=call.response_id,
        final_reply_text=reply,
        final_status=brain_output.status,
        context_id=effective_context_id,
        stage_timings_ms={"brain_call": latency_ms},
        memory_observability=memory_obs,
        nodes={"brain": node_trace},
    )

    repo.save_state(state, canonical_state)
    repo.save_recent_dialogue(state, recent_dialogue)
    repo.append_trace(state, turn_trace)
    save_session_state(state)

    meta = {
        "turn_id": turn_id,
        "pipeline_topology": "single_llm",
        "node_names": ["brain"],
        "llm_call_count": 1 if llm_call_attempted else 0,
        "response_id": call.response_id,
    }
    return reply, state, meta
