from __future__ import annotations

import json
import os
import time
import uuid
import logging
import re
from importlib import metadata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import openai
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from infra.openai.structured_outputs import (
    build_schema_observability,
    normalize_schema_for_strict_json_schema,
    validate_openai_structured_output_subset,
    validate_strict_json_schema,
)
from infra.runtime_version import get_runtime_version_info
from sessions.state import SessionState, add_message, save_session_state

from ..contexts import (
    read_bound_conversacion_simple_context_from_session,
    resolve_conversacion_simple_context_for_prompts_dir,
)
from ..nodes import BrainInput, BrainOutput, BrainTaskContract, DialogueMessage, TraceMeta, UserTurn
from ..memory import (
    flatten_turns,
    run_memory_maintenance_best_effort,
    schedule_memory_maintenance,
    should_schedule_compaction,
    trim_recent_dialogue_by_turns,
)
from ..state import (
    ConversationSimpleCanonicalState,
    ConversationSimpleMemoryEpisodicItem,
    build_default_conversation_simple_canonical_state,
)
from ..traces import ConversationSimpleTurnTrace, build_brain_node_trace
from .flow_config import ConversationSimpleTurnConfig
from negociacion.orchestration.flow_config import safe_invoke_tts_prefetch_hook
from negociacion.orchestration.turn_execution_context import TurnExecutionContext

logger = logging.getLogger(__name__)


def _is_truthy_env(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _is_trace_forensic_enabled() -> bool:
    return _is_truthy_env(os.getenv("CONVERSACION_SIMPLE_TRACE_FORENSIC"))


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
    recent_dialogue_short_max: int = 8,
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
        phase_cards=canonical_state.phase_cards,
        conversation_state=canonical_state.conversation_state,
        memory_working=canonical_state.memory_working,
        memory_compacted_summary=canonical_state.memory_compacted_summary,
        recent_dialogue_short=_compact_recent(recent_dialogue, recent_dialogue_short_max),
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
    schema_observability: dict[str, object] | None = None
    fallback_reason_code: str | None = None
    model_attempted: bool = False
    model_succeeded: bool = False
    provider_exception: dict[str, object | None] | None = None
    provider_request: dict[str, object] | None = None
    provider_response_text: str | None = None
    timings_ms: dict[str, float] | None = None
    retry_attempted: bool = False
    retry_succeeded: bool = False
    retry_reason: str | None = None
    parse_error_meta: dict[str, object] | None = None
    provider_response_diagnostics: dict[str, object | None] | None = None


_DEFAULT_SUMMARIZER_PROMPT = """Eres un summarizer táctico de contexto conversacional para negociación.
Devuelve SOLO JSON válido para el schema solicitado.
Objetivo: comprimir contexto antiguo sin inventar información y preservar continuidad operativa.
Reglas:
- Mantén orden temporal y causal.
- Si hay ambigüedad, explícitala en `uncertainties`.
- Si no hay evidencia suficiente para un campo, usa null o lista vacía.
- Prioriza hechos operativos sobre estilo narrativo.
- No respondas al usuario final.
- Nunca inventes propuestas, concesiones o acuerdos.
"""


class SummarizerTurnPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_index: int
    messages: list[DialogueMessage] = Field(default_factory=list)


class SummarizerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["summary_input.v1"]
    objective: str
    previous_summary: str
    archived_turns: list[SummarizerTurnPayload] = Field(default_factory=list)


class SummarizerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["memory_summary.v1"]
    situation_live: str
    active_proposal: str | None = None
    latest_offer_each_side: list[str] = Field(default_factory=list)
    concessions_accumulated: list[str] = Field(default_factory=list)
    open_items: list[str] = Field(default_factory=list)
    closed_items: list[str] = Field(default_factory=list)
    operative_constraints: list[str] = Field(default_factory=list)
    fixed_time_calculations: list[str] = Field(default_factory=list)
    operative_question_live: str | None = None
    sensitive_info_exposed: list[str] = Field(default_factory=list)
    agreement_progress: str | None = None
    pending_inconsistencies: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


@dataclass
class StructuredSummarizerCall:
    source: Literal["model", "fallback"]
    output: SummarizerOutput | None
    response_id: str | None = None
    schema_observability: dict[str, object] | None = None
    fallback_reason_code: str | None = None
    model_attempted: bool = False
    model_succeeded: bool = False
    provider_exception: dict[str, object | None] | None = None
    provider_request: dict[str, object] | None = None
    provider_response_text: str | None = None


_SANITIZE_PATTERN_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    # Bearer and token styles.
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b(api[-_ ]?key|access[-_ ]?token|refresh[-_ ]?token)\b\s*[:=]\s*['\"]?[^'\"\s,}]+"), r"\1=[REDACTED]"),
    # OpenAI keys.
    (re.compile(r"\bsk-[A-Za-z0-9]{10,}\b"), "[REDACTED_OPENAI_KEY]"),
    # Authorization header bodies.
    (re.compile(r"(?i)\b(authorization)\b\s*[:=]\s*([^\s,]+(?:\s+[^\s,]+)?)"), r"\1: [REDACTED]"),
]


def _sanitize_exception_message(raw_message: str | None, *, max_len: int = 500) -> str | None:
    if raw_message is None:
        return None
    sanitized = " ".join(raw_message.split())
    for pattern, replacement in _SANITIZE_PATTERN_REPLACEMENTS:
        sanitized = pattern.sub(replacement, sanitized)
    if len(sanitized) > max_len:
        return f"{sanitized[:max_len]}…[truncated]"
    return sanitized


def _extract_provider_exception_details(
    exc: Exception,
    *,
    stage: Literal["brain", "summarizer"],
    model: str,
) -> dict[str, object | None]:
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response_obj = getattr(exc, "response", None)
        status_code = getattr(response_obj, "status_code", None)
    provider_code = getattr(exc, "code", None)
    if provider_code is None:
        error_obj = getattr(exc, "error", None)
        provider_code = getattr(error_obj, "code", None)

    exc_text = str(exc)
    if not isinstance(status_code, int):
        status_match = re.search(r"(?i)\berror code\s*:\s*(\d{3})\b", exc_text)
        if status_match:
            status_code = int(status_match.group(1))
    if not isinstance(provider_code, str):
        code_match = re.search(r"['\"]code['\"]\s*:\s*['\"]([^'\"]+)['\"]", exc_text)
        if code_match:
            provider_code = code_match.group(1)

    return {
        "provider_exception_type": type(exc).__name__,
        "provider_exception_message": _sanitize_exception_message(exc_text),
        "provider_exception_status_code": status_code if isinstance(status_code, int) else None,
        "provider_exception_code": provider_code if isinstance(provider_code, str) else None,
        "provider_exception_stage": stage,
        "provider_model_target": model,
    }



def _safe_get_attr_or_key(obj: object, name: str) -> object | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _extract_response_diagnostics(response: object) -> dict[str, object | None]:
    """Return privacy-safe provider response metadata for Railway log triage.

    The fallback phrase is emitted after the Responses API call returns something
    the pipeline cannot turn into a BrainOutput.  These diagnostics deliberately
    avoid raw model text/user content and keep only structural metadata that helps
    tell apart incomplete/filtered/empty responses from local JSON parsing issues.
    """
    output = _safe_get_attr_or_key(response, "output")
    output_count = len(output) if isinstance(output, list) else None
    output_item_types: list[str] = []
    first_output_status = None
    if isinstance(output, list):
        for item in output[:5]:
            item_type = _safe_get_attr_or_key(item, "type")
            if isinstance(item_type, str):
                output_item_types.append(item_type)
        if output:
            first_output_status_raw = _safe_get_attr_or_key(output[0], "status")
            first_output_status = first_output_status_raw if isinstance(first_output_status_raw, str) else None

    incomplete_details = _safe_get_attr_or_key(response, "incomplete_details")
    incomplete_reason = None
    if incomplete_details is not None:
        reason_raw = _safe_get_attr_or_key(incomplete_details, "reason")
        incomplete_reason = reason_raw if isinstance(reason_raw, str) else None

    error_obj = _safe_get_attr_or_key(response, "error")
    error_code = None
    error_message = None
    if error_obj is not None:
        code_raw = _safe_get_attr_or_key(error_obj, "code")
        message_raw = _safe_get_attr_or_key(error_obj, "message")
        error_code = code_raw if isinstance(code_raw, str) else None
        error_message = _sanitize_exception_message(message_raw if isinstance(message_raw, str) else None)

    status_raw = _safe_get_attr_or_key(response, "status")
    return {
        "response_status": status_raw if isinstance(status_raw, str) else None,
        "response_incomplete_reason": incomplete_reason,
        "response_output_count": output_count,
        "response_output_item_types": output_item_types,
        "response_first_output_status": first_output_status,
        "response_error_code": error_code,
        "response_error_message": error_message,
    }


def _extract_output_text(response: object) -> str | None:
    output = getattr(response, "output_text", None)
    if isinstance(output, str) and output.strip():
        return output
    return None


def _build_json_parse_meta(text: str | None, exc: Exception | None = None) -> dict[str, object]:
    raw = text or ""
    stripped = raw.lstrip()
    first_non_ws_char = stripped[:1] if stripped else ""
    starts_with_code_fence = stripped.startswith("```")
    looks_like_json_object = first_non_ws_char == "{"
    parse_error_pos = None
    parse_error_msg = None
    if isinstance(exc, json.JSONDecodeError):
        parse_error_pos = exc.pos
        parse_error_msg = f"{exc.msg[:120]}"
    elif exc is not None:
        parse_error_msg = type(exc).__name__
    return {
        "output_len": len(raw),
        "first_non_ws_char": first_non_ws_char or None,
        "starts_with_code_fence": starts_with_code_fence,
        "looks_like_json_object": looks_like_json_object,
        "parse_error_pos": parse_error_pos,
        "parse_error_msg": parse_error_msg,
    }


def _extract_response_id(response: object) -> str | None:
    value = getattr(response, "id", None)
    return value if isinstance(value, str) and value.strip() else None


def _normalize_schema_for_strict_json_schema(schema: object) -> object:
    return normalize_schema_for_strict_json_schema(schema)


def _prepare_strict_schema(
    *,
    schema_name: str,
    schema: object,
    provider_model_target: str,
    format_name: str,
    format_strict: bool,
) -> tuple[object, dict[str, object]]:
    normalized = _normalize_schema_for_strict_json_schema(schema)
    validation_report = validate_strict_json_schema(normalized)
    subset_validation = validate_openai_structured_output_subset(normalized)
    observability = build_schema_observability(schema_name=schema_name, schema=normalized, validation_report=validation_report)
    observability["runtime_version"] = get_runtime_version_info()
    observability["openai_subset_validation"] = subset_validation
    return normalized, observability


def _package_version(package_name: str) -> str | None:
    try:
        return metadata.version(package_name)
    except Exception:
        return None


def _provider_runtime_fingerprint(
    *,
    client: openai.OpenAI | None,
    model_target: str,
    request_payload: dict[str, object] | None,
    schema_observability: dict[str, object] | None,
    forensic_enabled: bool = False,
) -> dict[str, object]:
    runtime = get_runtime_version_info()
    text_format = ((((request_payload or {}).get("text") or {}).get("format")) or {})
    schema = text_format.get("schema")
    root_properties_count = 0
    root_required_count = 0
    state_patch_properties_count = 0
    state_patch_required_count = 0
    root_properties: list[str] = []
    root_required: list[str] = []
    state_patch_properties: list[str] = []
    state_patch_required: list[str] = []
    if isinstance(schema, dict):
        props = schema.get("properties")
        req = schema.get("required")
        if isinstance(props, dict):
            root_properties = sorted(list(props.keys()))
            root_properties_count = len(root_properties)
        if isinstance(req, list):
            root_required = [str(item) for item in req]
            root_required_count = len(root_required)
        defs = schema.get("$defs")
        if isinstance(defs, dict):
            bsp = defs.get("BrainStatePatch")
            if isinstance(bsp, dict):
                bsp_props = bsp.get("properties")
                bsp_req = bsp.get("required")
                if isinstance(bsp_props, dict):
                    state_patch_properties = sorted(list(bsp_props.keys()))
                    state_patch_properties_count = len(state_patch_properties)
                if isinstance(bsp_req, list):
                    state_patch_required = [str(item) for item in bsp_req]
                    state_patch_required_count = len(state_patch_required)
    base_url = None
    if client is not None:
        maybe_base_url = getattr(client, "base_url", None)
        base_url = str(maybe_base_url) if maybe_base_url is not None else None
    validation = schema_observability.get("validation") if isinstance(schema_observability, dict) else {}
    first_mismatch = validation.get("first_mismatch") if isinstance(validation, dict) else None
    schema_hash = schema_observability.get("schema_hash") if isinstance(schema_observability, dict) else None
    fingerprint: dict[str, object] = {
        "git_commit": runtime.get("git_commit"),
        "build_id": runtime.get("build_id"),
        "service_version": runtime.get("service_version"),
        "deploy_env": runtime.get("deploy_env"),
        "openai_version": _package_version("openai"),
        "httpx_version": _package_version("httpx"),
        "provider_model_target": model_target,
        "base_url": base_url,
        "text_format_name": text_format.get("name") if isinstance(text_format, dict) else None,
        "text_format_strict": text_format.get("strict") if isinstance(text_format, dict) else None,
        "schema_hash": schema_hash,
        "root_properties_count": root_properties_count,
        "root_required_count": root_required_count,
        "brain_state_patch_properties_count": state_patch_properties_count,
        "brain_state_patch_required_count": state_patch_required_count,
        "first_mismatch": first_mismatch,
    }
    if forensic_enabled:
        fingerprint.update(
            {
                "root_properties": root_properties,
                "root_required": root_required,
                "brain_state_patch_properties": state_patch_properties,
                "brain_state_patch_required": state_patch_required,
                "schema_serialized": schema,
            }
        )
    return fingerprint


def _compact_schema_observability(
    schema_observability: dict[str, object] | None,
    *,
    forensic_enabled: bool,
) -> dict[str, object] | None:
    if not isinstance(schema_observability, dict):
        return None
    if forensic_enabled:
        return schema_observability
    validation = schema_observability.get("validation")
    subset_validation = schema_observability.get("openai_subset_validation")
    compact: dict[str, object] = {
        "schema_name": schema_observability.get("schema_name"),
        "schema_hash": schema_observability.get("schema_hash"),
        "validation": {
            "valid": validation.get("valid") if isinstance(validation, dict) else None,
            "first_mismatch": validation.get("first_mismatch") if isinstance(validation, dict) else None,
        },
        "openai_subset_validation": {
            "valid": subset_validation.get("valid") if isinstance(subset_validation, dict) else None,
            "first_violation": subset_validation.get("first_violation") if isinstance(subset_validation, dict) else None,
        },
    }
    return compact


def _call_brain_structured(
    *,
    client: openai.OpenAI | None,
    model: str,
    messages: list[dict[str, str]],
    max_output_tokens: int | None = None,
) -> StructuredBrainCall:
    timings_ms: dict[str, float] = {}
    total_started = time.perf_counter()
    if client is None:
        return StructuredBrainCall(
            source="fallback",
            parsed_json=None,
            response=None,
            fallback_reason_code="client_unavailable",
            model_attempted=False,
            model_succeeded=False,
            provider_exception=None,
            timings_ms=timings_ms,
        )
    schema_started = time.perf_counter()
    normalized_schema, schema_observability = _prepare_strict_schema(
        schema_name=BrainOutput.__name__,
        schema=BrainOutput.model_json_schema(),
        provider_model_target=model,
        format_name=BrainOutput.__name__,
        format_strict=True,
    )
    timings_ms["schema_prepare"] = round((time.perf_counter() - schema_started) * 1000, 3)
    validation = schema_observability.get("validation")
    subset_validation = schema_observability.get("openai_subset_validation")
    strict_valid = isinstance(validation, dict) and bool(validation.get("valid", False))
    subset_valid = isinstance(subset_validation, dict) and bool(subset_validation.get("valid", False))
    if not strict_valid or not subset_valid:
        logger.error(
            "conversacion_simple_schema_preflight_failed stage=brain schema_name=%s schema_hash=%s first_mismatch=%s subset_first_violation=%s runtime_version=%s",
            schema_observability.get("schema_name"),
            schema_observability.get("schema_hash"),
            validation.get("first_mismatch") if isinstance(validation, dict) else None,
            subset_validation.get("first_violation") if isinstance(subset_validation, dict) else None,
            schema_observability.get("runtime_version"),
        )
        return StructuredBrainCall(
            source="fallback",
            parsed_json=None,
            response=None,
            schema_observability=schema_observability,
            fallback_reason_code="schema_preflight_invalid",
            model_attempted=False,
            model_succeeded=False,
            provider_exception=None,
            timings_ms=timings_ms,
        )
    request_payload: dict[str, object] = {
        "model": model,
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": BrainOutput.__name__,
                "schema": normalized_schema,
                "strict": True,
            }
        },
        "reasoning": {"effort": "low"},
        "store": False,
    }
    if isinstance(max_output_tokens, int) and max_output_tokens > 0:
        request_payload["max_output_tokens"] = max_output_tokens
    try:
        provider_started = time.perf_counter()
        response = client.responses.create(**request_payload)
        timings_ms["provider_responses_create"] = round((time.perf_counter() - provider_started) * 1000, 3)
    except Exception as exc:
        provider_exception = _extract_provider_exception_details(exc, stage="brain", model=model)
        logger.exception(
            "conversacion_simple_structured_call_failed stage=brain schema_name=%s schema_hash=%s runtime_version=%s provider_exception_type=%s provider_exception_status_code=%s provider_exception_code=%s provider_model_target=%s provider_exception_message=%s",
            schema_observability.get("schema_name"),
            schema_observability.get("schema_hash"),
            schema_observability.get("runtime_version"),
            provider_exception["provider_exception_type"],
            provider_exception["provider_exception_status_code"],
            provider_exception["provider_exception_code"],
            provider_exception["provider_model_target"],
            provider_exception["provider_exception_message"],
        )
        return StructuredBrainCall(
            source="fallback",
            parsed_json=None,
            response=None,
            schema_observability=schema_observability,
            fallback_reason_code="provider_exception",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=provider_exception,
            provider_request=request_payload,
            timings_ms=timings_ms,
        )
    output_extract_started = time.perf_counter()
    text = _extract_output_text(response)
    response_id = _extract_response_id(response)
    response_diagnostics = _extract_response_diagnostics(response)
    timings_ms["extract_output_text"] = round((time.perf_counter() - output_extract_started) * 1000, 3)
    if not text:
        logger.warning(
            "conversacion_simple_brain_empty_output_text response_id=%s response_status=%s incomplete_reason=%s output_count=%s output_item_types=%s first_output_status=%s error_code=%s",
            response_id,
            response_diagnostics.get("response_status"),
            response_diagnostics.get("response_incomplete_reason"),
            response_diagnostics.get("response_output_count"),
            response_diagnostics.get("response_output_item_types"),
            response_diagnostics.get("response_first_output_status"),
            response_diagnostics.get("response_error_code"),
        )
        return StructuredBrainCall(
            source="fallback",
            parsed_json=None,
            response=response,
            response_id=response_id,
            schema_observability=schema_observability,
            fallback_reason_code="empty_output_text",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=None,
            provider_request=request_payload,
            timings_ms=timings_ms,
            provider_response_diagnostics=response_diagnostics,
        )
    try:
        json_load_started = time.perf_counter()
        payload = json.loads(text)
        timings_ms["json_loads"] = round((time.perf_counter() - json_load_started) * 1000, 3)
    except Exception as parse_exc:
        parse_meta = _build_json_parse_meta(text, parse_exc)
        logger.warning(
            "conversacion_simple_brain_json_parse_error response_id=%s output_len=%s first_non_ws_char=%s starts_with_code_fence=%s looks_like_json_object=%s parse_error_pos=%s",
            response_id,
            parse_meta.get("output_len"),
            parse_meta.get("first_non_ws_char"),
            parse_meta.get("starts_with_code_fence"),
            parse_meta.get("looks_like_json_object"),
            parse_meta.get("parse_error_pos"),
        )
        retry_payload = dict(request_payload)
        retry_input = list(messages)
        retry_input.append(
            {
                "role": "developer",
                "content": (
                    "Tu salida previa no fue JSON parseable. "
                    "Devuelve EXCLUSIVAMENTE un único objeto JSON válido para BrainOutput, "
                    "sin markdown, sin fences, sin texto adicional."
                ),
            }
        )
        retry_payload["input"] = retry_input
        try:
            retry_started = time.perf_counter()
            retry_response = client.responses.create(**retry_payload)
            timings_ms["provider_responses_retry_after_json_parse_error"] = round((time.perf_counter() - retry_started) * 1000, 3)
            retry_text = _extract_output_text(retry_response)
            retry_response_id = _extract_response_id(retry_response)
            if retry_text:
                retry_json_started = time.perf_counter()
                retry_payload_json = json.loads(retry_text)
                timings_ms["json_loads_retry_after_json_parse_error"] = round((time.perf_counter() - retry_json_started) * 1000, 3)
                logger.info(
                    "conversacion_simple_brain_retry_succeeded reason=json_parse_error response_id=%s",
                    retry_response_id,
                )
                timings_ms["total"] = round((time.perf_counter() - total_started) * 1000, 3)
                return StructuredBrainCall(
                    source="model",
                    parsed_json=retry_payload_json if isinstance(retry_payload_json, dict) else None,
                    response=retry_response,
                    response_id=retry_response_id,
                    schema_observability=schema_observability,
                    model_attempted=True,
                    model_succeeded=isinstance(retry_payload_json, dict),
                    provider_exception=None,
                    provider_request=retry_payload,
                    provider_response_text=None,
                    timings_ms=timings_ms,
                    provider_response_diagnostics=_extract_response_diagnostics(retry_response),
                    retry_attempted=True,
                    retry_succeeded=isinstance(retry_payload_json, dict),
                    retry_reason="json_parse_error",
                )
            retry_meta = _build_json_parse_meta(retry_text, None)
            logger.warning(
                "conversacion_simple_brain_retry_failed reason=json_parse_error response_id=%s output_len=%s starts_with_code_fence=%s looks_like_json_object=%s",
                retry_response_id,
                retry_meta.get("output_len"),
                retry_meta.get("starts_with_code_fence"),
                retry_meta.get("looks_like_json_object"),
            )
        except Exception as retry_exc:
            retry_meta = _build_json_parse_meta(locals().get("retry_text"), retry_exc)
            logger.warning(
                "conversacion_simple_brain_retry_failed reason=json_parse_error response_id=%s output_len=%s first_non_ws_char=%s starts_with_code_fence=%s looks_like_json_object=%s parse_error_pos=%s",
                locals().get("retry_response_id"),
                retry_meta.get("output_len"),
                retry_meta.get("first_non_ws_char"),
                retry_meta.get("starts_with_code_fence"),
                retry_meta.get("looks_like_json_object"),
                retry_meta.get("parse_error_pos"),
            )
        return StructuredBrainCall(
            source="fallback",
            parsed_json=None,
            response=response,
            response_id=response_id,
            schema_observability=schema_observability,
            fallback_reason_code="json_parse_error",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=None,
            provider_request=request_payload,
            provider_response_text=None,
            timings_ms=timings_ms,
            provider_response_diagnostics=response_diagnostics,
            retry_attempted=True,
            retry_succeeded=False,
            retry_reason="json_parse_error",
            parse_error_meta=parse_meta,
        )
    timings_ms["total"] = round((time.perf_counter() - total_started) * 1000, 3)
    return StructuredBrainCall(
        source="model",
        parsed_json=payload if isinstance(payload, dict) else None,
        response=response,
        response_id=response_id,
        schema_observability=schema_observability,
        model_attempted=True,
        model_succeeded=isinstance(payload, dict),
        provider_exception=None,
        provider_request=request_payload,
        provider_response_text=None,
        timings_ms=timings_ms,
        provider_response_diagnostics=response_diagnostics,
    )


def _build_summarizer_messages(*, summarizer_prompt: str, payload: SummarizerInput) -> list[dict[str, str]]:
    return [
        {"role": "developer", "content": summarizer_prompt},
        {
            "role": "user",
            "content": "<summary_input_json>\n"
            f"{payload.model_dump_json()}\n"
            "</summary_input_json>",
        },
    ]


def _call_summarizer_structured(
    *,
    client: openai.OpenAI | None,
    model: str,
    messages: list[dict[str, str]],
) -> StructuredSummarizerCall:
    if client is None:
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id=None,
            fallback_reason_code="client_unavailable",
            model_attempted=False,
            model_succeeded=False,
            provider_exception=None,
        )
    normalized_schema, schema_observability = _prepare_strict_schema(
        schema_name=SummarizerOutput.__name__,
        schema=SummarizerOutput.model_json_schema(),
        provider_model_target=model,
        format_name=SummarizerOutput.__name__,
        format_strict=True,
    )
    validation = schema_observability.get("validation")
    subset_validation = schema_observability.get("openai_subset_validation")
    strict_valid = isinstance(validation, dict) and bool(validation.get("valid", False))
    subset_valid = isinstance(subset_validation, dict) and bool(subset_validation.get("valid", False))
    if not strict_valid or not subset_valid:
        logger.error(
            "conversacion_simple_schema_preflight_failed stage=summarizer schema_name=%s schema_hash=%s first_mismatch=%s subset_first_violation=%s runtime_version=%s",
            schema_observability.get("schema_name"),
            schema_observability.get("schema_hash"),
            validation.get("first_mismatch") if isinstance(validation, dict) else None,
            subset_validation.get("first_violation") if isinstance(subset_validation, dict) else None,
            schema_observability.get("runtime_version"),
        )
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id=None,
            schema_observability=schema_observability,
            fallback_reason_code="schema_preflight_invalid",
            model_attempted=False,
            model_succeeded=False,
            provider_exception=None,
        )
    request_payload: dict[str, object] = {
        "model": model,
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": SummarizerOutput.__name__,
                "schema": normalized_schema,
                "strict": True,
            }
        },
        "reasoning": {"effort": "minimal"},
        "store": False,
    }
    try:
        response = client.responses.create(**request_payload)
    except Exception as exc:
        provider_exception = _extract_provider_exception_details(exc, stage="summarizer", model=model)
        logger.exception(
            "conversacion_simple_structured_call_failed stage=summarizer schema_name=%s schema_hash=%s runtime_version=%s provider_exception_type=%s provider_exception_status_code=%s provider_exception_code=%s provider_model_target=%s provider_exception_message=%s",
            schema_observability.get("schema_name"),
            schema_observability.get("schema_hash"),
            schema_observability.get("runtime_version"),
            provider_exception["provider_exception_type"],
            provider_exception["provider_exception_status_code"],
            provider_exception["provider_exception_code"],
            provider_exception["provider_model_target"],
            provider_exception["provider_exception_message"],
        )
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id=None,
            schema_observability=schema_observability,
            fallback_reason_code="provider_exception",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=provider_exception,
            provider_request=request_payload,
        )
    response_id = _extract_response_id(response)
    text = _extract_output_text(response)
    if not text:
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id=response_id,
            schema_observability=schema_observability,
            fallback_reason_code="empty_output_text",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=None,
            provider_request=request_payload,
        )
    try:
        payload = json.loads(text)
        output = SummarizerOutput.model_validate(payload)
    except Exception:
        return StructuredSummarizerCall(
            source="fallback",
            output=None,
            response_id=response_id,
            schema_observability=schema_observability,
            fallback_reason_code="json_parse_or_validation_error",
            model_attempted=True,
            model_succeeded=False,
            provider_exception=None,
            provider_request=request_payload,
            provider_response_text=text,
        )
    return StructuredSummarizerCall(
        source="model",
        output=output,
        response_id=response_id,
        schema_observability=schema_observability,
        fallback_reason_code=None,
        model_attempted=True,
        model_succeeded=True,
        provider_exception=None,
        provider_request=request_payload,
        provider_response_text=text,
    )


def _render_structured_summary(output: SummarizerOutput) -> str:
    payload = output.model_dump(mode="json")
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _truncate_compacted_summary(summary: str, max_chars: int) -> str:
    if not summary or max_chars <= 0:
        return summary
    if len(summary) <= max_chars:
        return summary
    return summary[:max_chars].rstrip()


def _format_turns_for_fallback_summary(*, archived_turns: list[list[DialogueMessage]]) -> str:
    lines: list[str] = []
    for turn_index, turn in enumerate(archived_turns, start=1):
        snippets = [f"{message.role}: {message.text}" for message in turn]
        lines.append(f"- turn_{turn_index}: {' | '.join(snippets)}")
    return "\n".join(lines)


def _resolve_summarizer_prompt(prompts_dir: Path) -> str:
    prompt_path = prompts_dir / "summarizer_prompt.txt"
    if prompt_path.exists():
        value = prompt_path.read_text(encoding="utf-8").strip()
        if value:
            return value
    return _DEFAULT_SUMMARIZER_PROMPT


def _brain_fallback(*, user_message: str, fallback_reason_code: str | None) -> BrainOutput:
    _ = user_message
    logger.info(
        "conversacion_simple_brain_fallback_emitted reason=%s user_message_len=%s",
        fallback_reason_code or "unknown_fallback",
        len(user_message or ""),
    )
    fallback_text = "No pude completar la generación del turno en este intento. ¿Puedes repetir tu último mensaje?"
    return BrainOutput(
        schema_version="brain.v1",
        status="clarify",
        assistant_response={"text": fallback_text},
        state_patch={
            "conversation_state": {"phase": None, "status": "active", "current_turn_goal": "pedir aclaración mínima", "closure_readiness": "not_ready"},
            "memory_working": {
                "current_topic": None,
                "pending_question": None,
                "last_turn_summary": f"fallback:{fallback_reason_code or 'unknown_fallback'}",
            },
            "memory_episodic_append": [],
        },
    )


def _normalize_reply_text(reply: str) -> str:
    normalized = " ".join(reply.strip().split())
    if not normalized:
        raise RuntimeError("conversacion_simple_invalid_assistant_response_text")
    return normalized


def _parse_brain_output_strict(
    *,
    payload: dict | None,
    allow_fallback: bool,
    user_message: str,
    fallback_reason_code: str | None = None,
) -> tuple[BrainOutput, str | None]:
    if payload is None:
        if allow_fallback:
            resolved_reason = fallback_reason_code or "unknown_fallback"
            return _brain_fallback(user_message=user_message, fallback_reason_code=resolved_reason), resolved_reason
        raise RuntimeError("conversacion_simple_brain_output_missing_json")
    try:
        output = BrainOutput.model_validate(payload)
    except ValidationError as exc:
        if allow_fallback:
            return _brain_fallback(user_message=user_message, fallback_reason_code="validation_error_after_parse"), "validation_error_after_parse"
        raise RuntimeError("conversacion_simple_brain_output_validation_error") from exc
    output.assistant_response.text = _normalize_reply_text(output.assistant_response.text)
    return output, None


def apply_brain_output_to_state(*, canonical_state: ConversationSimpleCanonicalState, brain_output: BrainOutput, turn_id: str) -> None:
    armed_prev = bool(canonical_state.ui_state.finish_button_armed)
    closure_ready_now = brain_output.state_patch.conversation_state.closure_readiness == "ready"
    canonical_state.conversation_state = brain_output.state_patch.conversation_state.model_copy(deep=True)
    canonical_state.memory_working = brain_output.state_patch.memory_working.model_copy(deep=True)
    append_items: list[ConversationSimpleMemoryEpisodicItem] = []
    for item in brain_output.state_patch.memory_episodic_append:
        event_type = item.event_type
        event_summary = item.event_summary
        if event_type not in {"important_fact", "intent", "constraint", "commitment"}:
            continue
        append_items.append(
            ConversationSimpleMemoryEpisodicItem(event_type=event_type, event_summary=event_summary, turn_id=item.turn_id or turn_id)
        )
    canonical_state.memory_episodic.extend(append_items)
    canonical_state.ui_state.finish_button_armed = armed_prev or closure_ready_now
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
    persist_state: bool = True,
) -> tuple[str, SessionState, dict[str, object]]:
    """Execute a single conversacion_simple turn.

    Parameters
    ----------
    persist_state:
        When ``True`` (default, preserves legacy behavior), the pipeline
        performs a final ``save_session_state(state)`` after all mutations.
        When ``False``, the caller is expected to persist the state itself
        (typically by calling ``persist_session_with_ttl`` which atomically
        saves + sets TTL in a single Redis round trip). The ``save_session_state``
        stage timing is still recorded so downstream instrumentation and
        tests keep observing a stable set of stage keys.
    """
    turn_started = time.perf_counter()
    stage_timings_ms: dict[str, int] = {}
    stage_timings_precise_ms: dict[str, float] = {}

    def _record_stage(name: str, started_at: float) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        stage_timings_precise_ms[name] = elapsed_ms
        stage_timings_ms[name] = int(elapsed_ms)

    validate_started = time.perf_counter()
    effective_context_id = _validate_turn_context(state=state, config=config, turn_context=turn_context)
    _record_stage("validate_turn_context", validate_started)
    repo_started = time.perf_counter()
    repo = ConversationSimpleStateRepository(
        memory_key=config.memory_key,
        recent_dialogue_key=config.recent_dialogue_key,
        traces_key=config.traces_key,
    )
    _record_stage("repository_init", repo_started)
    load_state_started = time.perf_counter()
    canonical_state = repo.load_state(state, config)
    _record_stage("load_canonical_state", load_state_started)
    load_recent_started = time.perf_counter()
    recent_dialogue = repo.load_recent_dialogue(state)
    _record_stage("load_recent_dialogue", load_recent_started)
    memory_obs: dict[str, object] = {}
    runtime_version = get_runtime_version_info()
    forensic_enabled = _is_trace_forensic_enabled()

    turn_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    user_turn_started = time.perf_counter()
    user_turn = _build_user_turn(user_message, now_iso)
    _record_stage("build_user_turn", user_turn_started)
    trace_meta = TraceMeta(
        turn_id=turn_id,
        prompt_version="brain_v1",
        schema_version="brain_input.v1",
        model_target=config.brain_model_target,
    )

    prompts_started = time.perf_counter()
    prompts_dir = Path(config.prompts_dir)
    prompt_text = (prompts_dir / "brain_prompt.txt").read_text(encoding="utf-8").strip()
    summarizer_prompt = _resolve_summarizer_prompt(prompts_dir)
    _record_stage("load_prompts", prompts_started)
    client_started = time.perf_counter()
    client = _build_client()
    _record_stage("build_openai_client", client_started)
    llm_call_attempted = client is not None

    add_user_started = time.perf_counter()
    add_message(state, role="user", content=user_message)
    recent_dialogue.append(DialogueMessage(role="user", text=user_turn.normalized_text))
    _record_stage("add_user_message", add_user_started)
    # TRIM AFTER USER MESSAGE: Determine if summarizer should trigger by comparing turn count
    # This is the trigger point for archiving old turns beyond context_limit_turns.
    trim_user_started = time.perf_counter()
    recent_dialogue, archived_turns, recent_metrics_user = trim_recent_dialogue_by_turns(
        recent_dialogue=recent_dialogue,
        context_limit_turns=config.context_limit_turns,
        keep_last_n_turns=config.keep_last_n_turns,
    )
    _record_stage("trim_recent_dialogue_after_user", trim_user_started)
    memory_obs.update(recent_metrics_user)
    if archived_turns:
        summarizer_input = SummarizerInput(
            schema_version="summary_input.v1",
            objective="resumir contexto antiguo de negociación para continuidad operativa",
            previous_summary=canonical_state.memory_compacted_summary,
            archived_turns=[
                SummarizerTurnPayload(turn_index=idx + 1, messages=turn)
                for idx, turn in enumerate(archived_turns)
            ],
        )
        summarizer_messages = _build_summarizer_messages(summarizer_prompt=summarizer_prompt, payload=summarizer_input)
        summarizer_started = time.perf_counter()
        summarizer_call = _call_summarizer_structured(
            client=client,
            model=config.summarizer_model_target,
            messages=summarizer_messages,
        )
        _record_stage("summarizer_call", summarizer_started)
        memory_obs["summarizer_runtime_fingerprint"] = _provider_runtime_fingerprint(
            client=client,
            model_target=config.summarizer_model_target,
            request_payload=summarizer_call.provider_request,
            schema_observability=summarizer_call.schema_observability,
            forensic_enabled=forensic_enabled,
        )
        if forensic_enabled and summarizer_call.provider_request is not None:
            memory_obs["summarizer_provider_request"] = summarizer_call.provider_request
        if forensic_enabled and isinstance(summarizer_call.provider_response_text, str):
            memory_obs["summarizer_provider_response_text"] = summarizer_call.provider_response_text
        compact_summarizer_schema_obs = _compact_schema_observability(
            summarizer_call.schema_observability,
            forensic_enabled=forensic_enabled,
        )
        if compact_summarizer_schema_obs is not None:
            memory_obs["summarizer_schema_observability"] = compact_summarizer_schema_obs
        if summarizer_call.output is not None:
            new_summary = _render_structured_summary(summarizer_call.output)
            canonical_state.memory_compacted_summary = _truncate_compacted_summary(new_summary, config.compacted_summary_max_chars)
            memory_obs["memory_summary_compaction_source"] = "llm_summarizer"
        else:
            fallback_block = _format_turns_for_fallback_summary(archived_turns=archived_turns)
            new_summary = "\n".join(
                part for part in [canonical_state.memory_compacted_summary.strip(), fallback_block] if part
            ).strip()
            canonical_state.memory_compacted_summary = _truncate_compacted_summary(new_summary, config.compacted_summary_max_chars)
            memory_obs["memory_summary_compaction_source"] = "deterministic_fallback"
            if summarizer_call.fallback_reason_code:
                memory_obs["summarizer_fallback_reason_code"] = summarizer_call.fallback_reason_code
            if summarizer_call.provider_exception is not None:
                memory_obs["summarizer_provider_exception"] = dict(summarizer_call.provider_exception)
        memory_obs["memory_summary_archived_turns"] = len(archived_turns)
        memory_obs["memory_summary_archived_messages"] = len(flatten_turns(turns=archived_turns))
    else:
        memory_obs["memory_summary_compaction_source"] = "not_needed"
        memory_obs["memory_summary_archived_turns"] = 0
        memory_obs["memory_summary_archived_messages"] = 0

    brain_input_started = time.perf_counter()
    brain_input = build_brain_input(
        canonical_state=canonical_state,
        recent_dialogue=recent_dialogue,
        user_turn=user_turn,
        trace_meta=trace_meta,
        recent_dialogue_short_max=config.recent_dialogue_short_max_messages,
    )
    _record_stage("build_brain_input", brain_input_started)
    brain_messages_started = time.perf_counter()
    brain_messages = build_brain_messages(prompt_text, brain_input)
    _record_stage("build_brain_messages", brain_messages_started)

    started = time.perf_counter()
    call = _call_brain_structured(
        client=client,
        model=trace_meta.model_target,
        messages=brain_messages,
        max_output_tokens=config.brain_max_output_tokens,
    )
    memory_obs["brain_runtime_fingerprint"] = _provider_runtime_fingerprint(
        client=client,
        model_target=trace_meta.model_target,
        request_payload=call.provider_request,
        schema_observability=call.schema_observability,
        forensic_enabled=forensic_enabled,
    )
    if forensic_enabled and call.provider_request is not None:
        memory_obs["brain_provider_request"] = call.provider_request
    if forensic_enabled and isinstance(call.provider_response_text, str):
        memory_obs["brain_provider_response_text"] = call.provider_response_text
    if call.provider_response_diagnostics is not None:
        memory_obs["brain_provider_response_diagnostics"] = call.provider_response_diagnostics
    compact_brain_schema_obs = _compact_schema_observability(call.schema_observability, forensic_enabled=forensic_enabled)
    if compact_brain_schema_obs is not None:
        memory_obs["brain_schema_observability"] = compact_brain_schema_obs
    parse_started = time.perf_counter()
    brain_output, parse_fallback_reason_code = _parse_brain_output_strict(
        payload=call.parsed_json,
        allow_fallback=True,
        user_message=user_message,
        fallback_reason_code=call.fallback_reason_code,
    )
    _record_stage("parse_and_validate_brain_output", parse_started)
    fallback_reason_code = parse_fallback_reason_code or (call.fallback_reason_code if call.source != "model" else None)
    model_attempted = call.model_attempted
    model_succeeded = call.source == "model" and fallback_reason_code is None
    model_called = model_succeeded
    memory_obs["brain_model_attempted"] = model_attempted
    memory_obs["brain_model_succeeded"] = model_succeeded
    if fallback_reason_code:
        memory_obs["brain_fallback_reason_code"] = fallback_reason_code
        logger.warning(
            "conversacion_simple_brain_fallback_activated session=%s turn_id=%s fallback_reason_code=%s model_attempted=%s model_succeeded=%s retry_attempted=%s retry_succeeded=%s retry_reason=%s user_message_len=%s parse_meta=%s",
            state.session_id,
            turn_id,
            fallback_reason_code,
            model_attempted,
            model_succeeded,
            call.retry_attempted,
            call.retry_succeeded,
            call.retry_reason,
            len(user_message or ""),
            call.parse_error_meta,
        )
    if call.provider_exception is not None:
        memory_obs["brain_provider_exception"] = dict(call.provider_exception)
    latency_ms = int((time.perf_counter() - started) * 1000)
    stage_timings_ms["brain_call"] = latency_ms
    stage_timings_precise_ms["brain_call"] = round((time.perf_counter() - started) * 1000, 3)
    provider_timings = call.timings_ms or {}
    if provider_timings:
        for key, value in provider_timings.items():
            stage_key = f"brain_call_{key}"
            stage_timings_precise_ms[stage_key] = value
            stage_timings_ms[stage_key] = int(value)

    # Apply deterministic patch
    patch_started = time.perf_counter()
    apply_brain_output_to_state(canonical_state=canonical_state, brain_output=brain_output, turn_id=turn_id)
    _record_stage("apply_brain_output_to_state", patch_started)

    assistant_state_started = time.perf_counter()
    reply = _normalize_reply_text(brain_output.assistant_response.text)
    # Kick TTS synthesis in parallel with the remaining persistence work.
    # The prefetch hook is non-blocking and must never raise: it schedules
    # an async job on the main event loop so that by the time the frontend
    # actually requests /tts for this reply the audio is already cached.
    # Total parallelism window: ~save_session_state + ~persist_session_with_ttl
    # + HTTP return + frontend /tts round-trip (~1-1.5s typical).
    safe_invoke_tts_prefetch_hook(reply)
    add_message(state, role="assistant", content=reply)
    recent_dialogue.append(DialogueMessage(role="assistant", text=reply))
    _record_stage("normalize_and_add_assistant_message", assistant_state_started)
    # TRIM AFTER ASSISTANT RESPONSE: Ensure total turn count stays within bounds after adding assistant message.
    # This second trim applies the same limit to maintain invariant: len(recent_dialogue_turns) <= keep_last_n_turns
    # Note: If the assistant message completes the 20th turn, this trim is a no-op. It only triggers if
    # adding the assistant would exceed keep_last_n_turns. In practice with context_limit_turns == keep_last_n_turns,
    # this is mostly idempotent, but necessary for consistency.
    trim_assistant_started = time.perf_counter()
    recent_dialogue, archived_turns_after_assistant, recent_metrics_assistant = trim_recent_dialogue_by_turns(
        recent_dialogue=recent_dialogue,
        context_limit_turns=config.context_limit_turns,
        keep_last_n_turns=config.keep_last_n_turns,
    )
    _record_stage("trim_recent_dialogue_after_assistant", trim_assistant_started)
    memory_obs.update(recent_metrics_assistant)
    if archived_turns_after_assistant:
        memory_obs["memory_post_assistant_archived_turns"] = len(archived_turns_after_assistant)

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
    maintenance_started = time.perf_counter()
    maintenance_obs = run_memory_maintenance_best_effort(
        canonical_state=canonical_state,
        high_resolution_limit=config.max_episodic_high_resolution_items,
        compacted_summary_max_chars=config.compacted_summary_max_chars,
        simulate_failure=config.maintenance_force_failure,
    )
    _record_stage("memory_maintenance", maintenance_started)
    memory_obs.update(maintenance_obs)

    node_trace_started = time.perf_counter()
    node_trace = build_brain_node_trace(
        latency_ms=latency_ms,
        status=brain_output.status,
        model_called=model_called,
        model_attempted=model_attempted,
        model_succeeded=model_succeeded,
        fallback_reason_code=fallback_reason_code,
        recent_dialogue_count=len(brain_input.recent_dialogue_short),
        episodic_append_count=len(brain_output.state_patch.memory_episodic_append),
        closure_readiness=brain_output.state_patch.conversation_state.closure_readiness,
        finish_button_armed=canonical_state.ui_state.finish_button_armed,
        finish_button_latched=canonical_state.ui_state.finish_button_armed and brain_output.state_patch.conversation_state.closure_readiness != "ready",
        provider_exception=call.provider_exception,
        include_provider_exception_details=forensic_enabled,
    )
    _record_stage("build_brain_node_trace", node_trace_started)

    turn_trace_started = time.perf_counter()
    turn_trace = ConversationSimpleTurnTrace(
        turn_id=turn_id,
        timestamp_utc=now_iso,
        session_id=state.session_id,
        user_id=state.user_id,
        previous_response_id_after=call.response_id,
        user_turn=user_turn,
        final_reply_text=reply,
        final_status=brain_output.status,
        closure_readiness=brain_output.state_patch.conversation_state.closure_readiness,
        finish_button_armed=canonical_state.ui_state.finish_button_armed,
        finish_button_latched=canonical_state.ui_state.finish_button_armed and brain_output.state_patch.conversation_state.closure_readiness != "ready",
        brain_model_attempted=model_attempted,
        brain_model_succeeded=model_succeeded,
        brain_fallback_reason_code=fallback_reason_code,
        context_id=effective_context_id,
        stage_timings_ms=stage_timings_ms,
        memory_observability=memory_obs,
        nodes={"brain": node_trace},
        runtime_version=runtime_version,
    )
    _record_stage("build_turn_trace", turn_trace_started)

    save_canonical_started = time.perf_counter()
    repo.save_state(state, canonical_state)
    _record_stage("save_canonical_state", save_canonical_started)
    save_recent_started = time.perf_counter()
    repo.save_recent_dialogue(state, recent_dialogue)
    _record_stage("save_recent_dialogue", save_recent_started)
    append_trace_started = time.perf_counter()
    repo.append_trace(state, turn_trace)
    _record_stage("append_turn_trace", append_trace_started)
    persist_started = time.perf_counter()
    if persist_state:
        save_session_state(state)
    # Always record the save_session_state stage key so downstream
    # instrumentation and tests observe a stable set of timings, even when
    # the caller opts to persist the state itself via persist_session_with_ttl.
    _record_stage("save_session_state", persist_started)
    _record_stage("turn_total", turn_started)

    meta = {
        "turn_id": turn_id,
        "pipeline_topology": "single_llm",
        "node_names": ["brain"],
        "llm_call_count": 1 if llm_call_attempted else 0,
        "response_id": call.response_id,
        "closure_readiness": brain_output.state_patch.conversation_state.closure_readiness,
        "finish_button_armed": canonical_state.ui_state.finish_button_armed,
        "stage_timings_ms": stage_timings_ms,
        "stage_timings_precise_ms": stage_timings_precise_ms,
        "brain_fallback_reason_code": fallback_reason_code,
    }
    return reply, state, meta
