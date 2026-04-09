from __future__ import annotations

import logging
from typing import Any
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from sessions.lifecycle import apply_session_ttl, touch_existing_session_if_present
from sessions.session_lock import SessionBusyError, acquire_session_execution_lock
from sessions.state import SessionState, get_session_state, get_session_store
from sessions.surface_scope import ensure_session_surface

from ..orchestration.flow_config import build_negotiation_pipeline_config
from ..orchestration.context_errors import ContextContractError
from ..orchestration.context_errors import SessionContextConflictError
from ..orchestration.turn_contract import execute_turn_with_contract  # backward-compatible patch target for tests/tooling
from conversacion_simple.orchestration.pipeline import run_conversacion_simple_turn  # backward-compatible patch target for tests/tooling
from ..state.canonical_state import build_default_canonical_state
from ..state.shared_types import ThreadMode
from ..traces.context_meta import build_trace_context_meta
from . import context_bridge, datasets_bridge, evals_bridge, experiments_bridge, guardrails_bridge, session_bridge, storage, trace_reader
from .flow_adapters import get_adapter, list_supported_flow_ids
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from ..services.context_http import raise_http_from_context_error
from ..forensics.provider_probe import begin_turn_probe, end_turn_probe

logger = logging.getLogger(__name__)


def _diagnostic_from_exception(exc: Exception) -> str:
    chain: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        text = str(current).strip()
        if text:
            chain.append(text)
        current = current.__cause__
    joined = " | ".join(chain)
    return joined[:600] if joined else type(exc).__name__


def _classify_exception(exc: Exception, *, failing_stage: str | None = None) -> dict[str, Any]:
    diagnostic = _diagnostic_from_exception(exc)
    normalized = diagnostic.lower()
    is_socket_write_timeout = "timeout writing to socket" in normalized or (
        "timeout" in normalized and "socket" in normalized and "write" in normalized
    )
    storage_stages = {
        "acquire_session_execution_lock",
        "touch_existing_session_if_present",
        "get_session_state",
        "apply_session_ttl_turn_completed",
    }
    if is_socket_write_timeout:
        if failing_stage in storage_stages:
            category = "session_storage_write_timeout"
        else:
            category = "upstream_write_timeout"
        return {
            "diagnostic": diagnostic,
            "error_category": category,
            "retryable": True,
            "failing_stage": failing_stage or "unknown",
        }
    return {
        "diagnostic": diagnostic,
        "error_category": "internal_turn_failure",
        "retryable": False,
        "failing_stage": failing_stage or "unknown",
    }


def _count_model_calls_from_trace(trace: dict[str, Any] | None) -> int:
    if not isinstance(trace, dict):
        return 0
    logs = trace.get("logs")
    if not isinstance(logs, list):
        return 0
    return sum(1 for item in logs if isinstance(item, dict) and bool(item.get("model_called", False)))


def _append_attempt_trace(state: SessionState, payload: dict[str, Any]) -> None:
    traces = state.world_state.setdefault("optimizador_attempt_traces", [])
    if not isinstance(traces, list):
        traces = []
        state.world_state["optimizador_attempt_traces"] = traces
    traces.append(payload)

def _apply_contextual_state_overrides(state: Any, config: Any, entries: list[dict[str, Any]], *, flow_id: str | None = None) -> None:
    persona_entry = next((entry for entry in entries if entry.get("category") == "contextual" and entry.get("key") == "persona"), None)
    if not persona_entry:
        return
    memory_key = config.memory_key
    raw = state.world_state.get(memory_key)
    if not isinstance(raw, dict):
        if flow_id == "conversacion_simple":
            from conversacion_simple.state import build_default_conversation_simple_canonical_state
            raw = build_default_conversation_simple_canonical_state(
                session_id=state.session_id,
                user_id=state.user_id,
                thread_mode=ThreadMode.conversation,
                context_id=getattr(config, "context_id", None),
            ).model_dump(mode="json")
        else:
            raw = build_default_canonical_state(session_id=state.session_id, user_id=state.user_id, thread_mode=ThreadMode.conversation).model_dump(mode="json")
    persona_value = persona_entry.get("value")
    if not isinstance(persona_value, dict):
        return
    import copy

    updated = copy.deepcopy(raw)
    if flow_id == "conversacion_simple":
        updated["persona"] = persona_value
    else:
        policy = persona_value.get("policy")
        expressive = persona_value.get("expressive")
        if not isinstance(policy, dict) or not isinstance(expressive, dict):
            return
        updated["persona"] = {"policy": policy, "expressive": expressive}
    state.world_state[memory_key] = updated


def _resolve_optimizer_contract_flags(state: SessionState) -> tuple[bool, bool]:
    if not isinstance(state.world_state, dict):
        return False, False
    meta = state.world_state.get("optimizador_sandbox_meta", {})
    if not isinstance(meta, dict):
        return False, False
    strategy = str(meta.get("clone_strategy") or "")
    clone_used = strategy == "full_session_with_preferred_conversation"
    new_conversation = strategy == "new_conversation_clean_start"
    return clone_used, new_conversation


def list_sessions() -> list[dict[str, Any]]:
    return session_bridge.list_sessions()


def list_attempt_traces(user_id: str, session_id: str) -> list[dict[str, Any]]:
    state = storage.get_optimizer_state(user_id, session_id)
    if state is None or not isinstance(state.world_state, dict):
        return []
    raw = state.world_state.get("optimizador_attempt_traces", [])
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]



def ensure_session(*, user_id: str, session_id: str, context_id: str | None = None, flow_id: str | None = None) -> dict[str, Any]:
    try:
        store = get_session_store()
        existing_state = store.get(user_id=user_id, session_id=session_id)
        state = existing_state or get_session_state(user_id=user_id, session_id=session_id)
        ensure_session_surface(state=state, surface='optimizador')
        base_context = context_bridge.ensure_optimizer_session_context(
            state=state,
            requested_context_id=context_id,
            requested_flow_id=flow_id,
        )
        adapter = get_adapter(base_context["flow_id"])
        traces = storage.resolve_traces(state)
        meta = state.world_state.get("optimizador_sandbox_meta", {}) if isinstance(state.world_state, dict) else {}
        ttl_scope = "bootstrap" if existing_state is None and len(traces) == 0 else "active"
        ttl_seconds = apply_session_ttl(state, scope=ttl_scope, reason="optimizador_bootstrap")
        logger.info(
            "optimizador_session_ready session=%s context=%s traces=%s ttl_scope=%s ttl_seconds=%s existing=%s",
            f"{user_id}:{session_id}",
            base_context["context_id"],
            len(traces),
            ttl_scope,
            ttl_seconds,
            existing_state is not None,
        )
        return {
            "session_key": storage.session_key(user_id, session_id),
            "user_id": user_id,
            "session_id": session_id,
            "turn_count": len(traces),
            "last_updated": state.last_updated.isoformat(),
            "is_sandbox": bool(meta),
            "sandbox_meta": meta if isinstance(meta, dict) else {},
            "base_context": base_context,
            "capabilities": adapter.capabilities().__dict__,
            "available_flows": list_supported_flow_ids(),
        }
    except ContextContractError as exc:
        raise_http_from_context_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

def list_conversations(user_id: str, session_id: str) -> list[dict[str, Any]]:
    return session_bridge.list_conversations(user_id, session_id)


def list_turns(user_id: str, session_id: str, conversation_id: str | None = None) -> list[dict[str, Any]]:
    return trace_reader.list_turns(user_id=user_id, session_id=session_id, conversation_id=conversation_id)


def get_turn(turn_id: str) -> dict[str, Any] | None:
    return trace_reader.get_turn(turn_id)


def get_dialogue(user_id: str, session_id: str) -> list[dict[str, Any]]:
    return trace_reader.get_dialogue(user_id=user_id, session_id=session_id)


def get_guardrails(turn_id: str) -> dict[str, Any] | None:
    turn = get_turn(turn_id)
    return guardrails_bridge.summarize_guardrails(turn) if turn else None


def duplicate_sandbox_session(
    *,
    optimizer_session_id: str,
    source_user_id: str,
    source_session_id: str,
    source_conversation_id: str | None,
    context_id: str | None = None,
) -> dict[str, Any]:
    try:
        return session_bridge.duplicate_sandbox_session(
            source_user_id=source_user_id,
            source_session_id=source_session_id,
            source_conversation_id=source_conversation_id,
            optimizer_session_id=optimizer_session_id,
            context_id=context_id,
        )
    except SessionContextConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "optimizer_context_conflict",
                "existing_context_id": exc.expected,
                "requested_context_id": exc.actual,
            },
        ) from exc


def new_conversation_session(*, optimizer_session_id: str, user_id: str, session_id: str, context_id: str | None = None) -> dict[str, Any]:
    try:
        state = get_session_state(user_id=user_id, session_id=session_id)
        ensure_session_surface(state=state, surface='optimizador')
        new_session_id = f"{session_id}__newconv__{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:6]}"
        new_state = SessionState(user_id=user_id, session_id=new_session_id)
        base_context = context_bridge.inherit_or_bind_sandbox_context(
            source_state=state,
            target_state=new_state,
            requested_context_id=context_id,
        )
        new_state.world_state["optimizador_sandbox_meta"] = {
            "optimizer_session_id": optimizer_session_id,
            "source_user_id": user_id,
            "source_session_id": session_id,
            "source_conversation_id": None,
            "clone_strategy": "new_conversation_clean_start",
            "cloned_at": datetime.now(timezone.utc).isoformat(),
            "preferred_conversation_id": None,
            "base_context": base_context,
        }
        ensure_session_surface(state=new_state, surface='optimizador')
        get_session_store().save(new_state)
        apply_session_ttl(new_state, scope="active", reason="optimizador_new_conversation")
        logger.info("optimizador_new_conversation_created source_session=%s new_session=%s", session_id, new_session_id)
        _ = state
        return {
            "session_key": storage.session_key(user_id, new_session_id),
            "user_id": user_id,
            "session_id": new_session_id,
            "sandbox_meta": new_state.world_state["optimizador_sandbox_meta"],
            "base_context": base_context,
        }
    except SessionContextConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "optimizer_context_conflict",
                "existing_context_id": exc.expected,
                "requested_context_id": exc.actual,
            },
        ) from exc
    except ContextContractError as exc:
        raise_http_from_context_error(exc)


def run_sandbox_turn(
    *,
    optimizer_session_id: str,
    user_id: str,
    session_id: str,
    message: str,
    conversation_id: str | None,
    scope_turn_id: str | None,
    repeat_from_turn_id: str | None,
    client_request_id: str | None = None,
    logical_user_message_id: str | None = None,
    logical_attempt_index: int | None = None,
) -> dict[str, Any]:
    failing_stage = "acquire_session_execution_lock"
    backend_turn_attempt_id = f"opt_attempt_{uuid4().hex[:12]}"
    attempt_started_at = datetime.now(timezone.utc).isoformat()
    trace_count_before = 0
    state: SessionState | None = None
    base_context: dict[str, Any] | None = None
    post_commit_housekeeping_error: str | None = None
    probe_snapshot = None
    try:
        with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
            failing_stage = "touch_existing_session_if_present"
            touch_ttl = touch_existing_session_if_present(
                user_id=user_id,
                session_id=session_id,
                scope="active",
                reason="optimizador_turn_lock_acquired",
            )
            logger.info(
                "optimizador_turn_started session=%s optimizer_session_id=%s ttl_seconds=%s client_request_id=%s",
                f"{user_id}:{session_id}",
                optimizer_session_id,
                touch_ttl,
                client_request_id,
            )
            failing_stage = "get_session_state"
            state = get_session_state(user_id=user_id, session_id=session_id)
            ensure_session_surface(state=state, surface='optimizador')
            trace_count_before = len(storage.resolve_traces(state))
            base_context = context_bridge.ensure_optimizer_session_context(state=state)
            adapter = get_adapter(base_context["flow_id"])
            failing_stage = "build_pipeline_config"
            if adapter.flow_id == "conversacion_simple":
                base_config = build_conversacion_simple_pipeline_config(context_id=base_context["context_id"], stateful=True)
            else:
                base_config = build_negotiation_pipeline_config(context_id=base_context["context_id"], stateful=True)
            resolved_entries = experiments_bridge.resolve_entries(
                optimizer_session_id=optimizer_session_id,
                conversation_id=conversation_id,
                turn_id=scope_turn_id,
            )
            config, tempdir = experiments_bridge.apply_overrides(base_config, resolved_entries, context_id=base_context["context_id"], flow_id=base_context["flow_id"])
            _apply_contextual_state_overrides(state, config, resolved_entries, flow_id=base_context["flow_id"])
            clone_used, new_conversation = _resolve_optimizer_contract_flags(state)
            probe_token = begin_turn_probe(
                logical_user_message_id=logical_user_message_id,
                logical_attempt_index=logical_attempt_index,
                client_request_id=client_request_id,
                backend_turn_attempt_id=backend_turn_attempt_id,
            )
            probe_snapshot = None
            try:
                failing_stage = "execute_turn_with_contract"
                reply, _, meta = adapter.run_sandbox_turn(
                    state=state,
                    user_message=message,
                    context_id=base_context["context_id"],
                    overrides_applied=bool(resolved_entries),
                    new_conversation=new_conversation,
                    clone_used=clone_used,
                    base_config=config,
                )
            finally:
                probe_snapshot = end_turn_probe(probe_token)
                if tempdir is not None:
                    tempdir.cleanup()
            failing_stage = "apply_session_ttl_turn_completed"
            try:
                apply_session_ttl(state, scope="active", reason="optimizador_turn_completed")
            except Exception as post_commit_exc:
                post_commit_housekeeping_error = _diagnostic_from_exception(post_commit_exc)
                logger.warning(
                    "optimizador_turn_post_commit_housekeeping_failed session=%s client_request_id=%s logical_user_message_id=%s logical_attempt_index=%s backend_turn_attempt_id=%s error=%s",
                    f"{user_id}:{session_id}",
                    client_request_id,
                    logical_user_message_id,
                    logical_attempt_index,
                    backend_turn_attempt_id,
                    post_commit_housekeeping_error,
                )
            latest_after = storage.resolve_traces(state)[-1] if storage.resolve_traces(state) else None
            _append_attempt_trace(
                state,
                {
                    "backend_turn_attempt_id": backend_turn_attempt_id,
                    "client_request_id": client_request_id,
                    "logical_user_message_id": logical_user_message_id,
                    "logical_attempt_index": logical_attempt_index,
                    "status": "success" if post_commit_housekeeping_error is None else "success_with_housekeeping_error",
                    "failing_stage": None,
                    "error_category": None,
                    "retryable": False,
                    "post_commit_housekeeping_error": post_commit_housekeeping_error,
                    "session_id": session_id,
                    "context_id": (base_context or {}).get("context_id"),
                    "trace_count_before": trace_count_before,
                    "trace_count_after": len(storage.resolve_traces(state)),
                    "model_calls_in_latest_trace": _count_model_calls_from_trace(latest_after),
                    "provider_calls_in_latest_trace": len(latest_after.get("provider_calls", [])) if isinstance(latest_after, dict) else 0,
                    "conversation_id_before": latest_after.get("conversation_id_before") if isinstance(latest_after, dict) else None,
                    "conversation_id_after": latest_after.get("conversation_id_after") if isinstance(latest_after, dict) else None,
                    "previous_response_id_before": latest_after.get("previous_response_id_before") if isinstance(latest_after, dict) else None,
                    "previous_response_id_after": latest_after.get("previous_response_id_after") if isinstance(latest_after, dict) else None,
                    "provider_calls_in_attempt": len(probe_snapshot.provider_calls) if probe_snapshot is not None else 0,
                    "side_effect_hooks_in_attempt": len(probe_snapshot.side_effect_hooks) if probe_snapshot is not None else 0,
                    "attempt_started_at": attempt_started_at,
                    "attempt_finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
    except SessionBusyError as exc:
        touch_existing_session_if_present(
            user_id=exc.user_id,
            session_id=exc.session_id,
            scope="active",
            reason="optimizador_turn_busy",
        )
        logger.warning(
            "optimizador_turn_busy session=%s retry_after=%s backend=%s",
            f"{exc.user_id}:{exc.session_id}",
            exc.retry_after_seconds,
            exc.lock_backend,
        )
        raise HTTPException(
            status_code=423,
            detail={
                "error": "session_busy",
                "user_id": exc.user_id,
                "session_id": exc.session_id,
                "retry_after_seconds": exc.retry_after_seconds,
                "lock_backend": exc.lock_backend,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except Exception as exc:
        if isinstance(exc, ContextContractError):
            raise_http_from_context_error(exc)
        error_id = f"opt_turn_{uuid4().hex[:10]}"
        classified = _classify_exception(exc, failing_stage=failing_stage)
        logger.exception(
            "optimizador_turn_failed error_id=%s session=%s optimizer_session_id=%s message_len=%s cause=%s error_category=%s retryable=%s failing_stage=%s client_request_id=%s logical_user_message_id=%s logical_attempt_index=%s backend_turn_attempt_id=%s diagnostic=%s",
            error_id,
            f"{user_id}:{session_id}",
            optimizer_session_id,
            len(message or ""),
            type(exc).__name__,
            classified["error_category"],
            classified["retryable"],
            classified["failing_stage"],
            client_request_id,
            logical_user_message_id,
            logical_attempt_index,
            backend_turn_attempt_id,
            classified["diagnostic"],
        )
        state_for_attempt = state or get_session_store().get(user_id=user_id, session_id=session_id)
        if isinstance(state_for_attempt, SessionState):
            latest_after = storage.resolve_traces(state_for_attempt)[-1] if storage.resolve_traces(state_for_attempt) else None
            _append_attempt_trace(
                state_for_attempt,
                {
                    "backend_turn_attempt_id": backend_turn_attempt_id,
                    "client_request_id": client_request_id,
                    "logical_user_message_id": logical_user_message_id,
                    "logical_attempt_index": logical_attempt_index,
                    "status": "failed",
                    "failing_stage": classified["failing_stage"],
                    "error_category": classified["error_category"],
                    "retryable": classified["retryable"],
                    "diagnostic": classified["diagnostic"],
                    "error_id": error_id,
                    "session_id": session_id,
                    "context_id": (base_context or {}).get("context_id"),
                    "trace_count_before": trace_count_before,
                    "trace_count_after": len(storage.resolve_traces(state_for_attempt)),
                    "model_calls_in_latest_trace": _count_model_calls_from_trace(latest_after),
                    "provider_calls_in_attempt": len(probe_snapshot.provider_calls) if probe_snapshot is not None else 0,
                    "side_effect_hooks_in_attempt": len(probe_snapshot.side_effect_hooks) if probe_snapshot is not None else 0,
                    "attempt_started_at": attempt_started_at,
                    "attempt_finished_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "turn_execution_failed",
                "error_id": error_id,
                "backend_turn_attempt_id": backend_turn_attempt_id,
                "cause": type(exc).__name__,
                "diagnostic": classified["diagnostic"],
                "error_category": classified["error_category"],
                "retryable": classified["retryable"],
                "failing_stage": classified["failing_stage"],
                "client_request_id": client_request_id,
                "logical_user_message_id": logical_user_message_id,
                "logical_attempt_index": logical_attempt_index,
                "message": "No se pudo procesar el turno en este momento. Inténtalo de nuevo.",
            },
        ) from exc

    traces = storage.resolve_traces(state)
    latest = traces[-1] if traces else None
    versioning = _resolve_versioning(state, latest, repeat_from_turn_id)
    if latest is not None:
        optimizer_state = experiments_bridge.get_state(optimizer_session_id)
        latest["_optimizador"] = {
            "optimizer_session_id": optimizer_session_id,
            "used_overrides": bool(resolved_entries),
            "applied_overrides": experiments_bridge.describe_effective_overrides(resolved_entries),
            "mode": optimizer_state.get("mode", "mirror"),
            "workspace_version": optimizer_state.get("workspace_version", 1),
            "session_key": storage.session_key(user_id, session_id),
            "conversation_id": conversation_id,
            "versioning": versioning,
            "base_context": build_trace_context_meta(state=state, overrides_applied=bool(resolved_entries)).model_dump(mode="json"),
            "capabilities": adapter.capabilities().__dict__,
        }

    turns = list_turns(user_id, session_id, conversation_id=conversation_id)
    selected_turn = turns[-1] if turns else None
    return {
        "reply": reply,
        "turn": selected_turn,
        "backend_turn_attempt_id": backend_turn_attempt_id,
        "post_commit_housekeeping_error": post_commit_housekeeping_error,
        "turn_title": derive_turn_title(latest, turns) if latest else None,
        "effective_overrides": experiments_bridge.describe_effective_overrides(resolved_entries),
        "entry_contract": meta.get("entry_contract") if isinstance(meta, dict) else None,
    }


def _resolve_versioning(state: Any, latest_turn: dict[str, Any] | None, repeat_from_turn_id: str | None) -> dict[str, Any]:
    if latest_turn is None:
        return {"base_turn_id": None, "version": 1}

    traces = storage.resolve_traces(state)
    if not repeat_from_turn_id:
        return {"base_turn_id": latest_turn.get("turn_id"), "version": 1}

    source_turn = next((t for t in traces if t.get("turn_id") == repeat_from_turn_id), None)
    base_turn_id = repeat_from_turn_id
    if isinstance(source_turn, dict):
        meta = source_turn.get("_optimizador", {}) if isinstance(source_turn.get("_optimizador"), dict) else {}
        versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
        base_turn_id = versioning.get("base_turn_id") or repeat_from_turn_id

    max_version = 1
    for t in traces:
        meta = t.get("_optimizador", {}) if isinstance(t.get("_optimizador"), dict) else {}
        versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
        if versioning.get("base_turn_id") == base_turn_id:
            max_version = max(max_version, int(versioning.get("version") or 1))

    return {"base_turn_id": base_turn_id, "version": max_version + 1}


def derive_turn_title(turn: dict[str, Any], turns: list[dict[str, Any]]) -> str:
    turn_id = turn.get("turn_id")
    index = next((item.get("index") for item in turns if item.get("turn_id") == turn_id), None)
    meta = turn.get("_optimizador", {}) if isinstance(turn.get("_optimizador"), dict) else {}
    versioning = meta.get("versioning", {}) if isinstance(meta.get("versioning"), dict) else {}
    version = versioning.get("version") or 1
    return f"Turno {index or '?'} · v{version}"


def list_prompts(*, user_id: str | None = None, session_id: str | None = None, context_id: str | None = None) -> list[dict[str, str]]:
    resolved_context_id = (context_id or '').strip() or None
    resolved_flow_id: str | None = None
    if user_id and session_id:
        state = storage.get_optimizer_state(user_id, session_id)
        if state is None:
            raise ValueError('sesión optimizer no encontrada')
        base_context = context_bridge.ensure_optimizer_session_context(state=state)
        resolved_context_id = base_context['context_id']
        resolved_flow_id = base_context.get("flow_id")
    if resolved_flow_id is None and resolved_context_id:
        resolved_flow_id = context_bridge.resolve_optimizer_context_payload(context_id=resolved_context_id)["flow_id"]
    adapter = get_adapter(resolved_flow_id or "negociacion")
    return adapter.list_prompts(context_id=resolved_context_id)


def list_contexts(*, flow_id: str | None = None) -> list[dict[str, Any]]:
    normalized_flow = (flow_id or "").strip() or None
    if normalized_flow:
        return get_adapter(normalized_flow).list_contexts()
    items: list[dict[str, Any]] = []
    for supported in list_supported_flow_ids():
        items.extend(get_adapter(supported).list_contexts())
    return items


def run_eval(action: str) -> dict[str, Any]:
    return evals_bridge.run_eval(action)


def save_case(turn_id: str, family: str, tags: list[str], notes: str) -> dict[str, Any]:
    turn = get_turn(turn_id)
    if not turn:
        raise ValueError("turn_id no encontrado")
    return datasets_bridge.save_case(turn, family=family, tags=tags, notes=notes)


def list_cases() -> list[dict[str, Any]]:
    return datasets_bridge.list_cases()


def compare_turns(turn_a: str, turn_b: str) -> dict[str, Any]:
    a = get_turn(turn_a)
    b = get_turn(turn_b)
    if not a or not b:
        raise ValueError("Turnos no encontrados")

    a_meta = a.get("_optimizador", {}) if isinstance(a.get("_optimizador"), dict) else {}
    b_meta = b.get("_optimizador", {}) if isinstance(b.get("_optimizador"), dict) else {}
    a_base = a_meta.get("base_context", {}) if isinstance(a_meta.get("base_context"), dict) else {}
    b_base = b_meta.get("base_context", {}) if isinstance(b_meta.get("base_context"), dict) else {}
    a_flow = a_base.get("flow_id")
    b_flow = b_base.get("flow_id")
    if a_flow and b_flow and a_flow != b_flow:
        raise ValueError(f"cross_flow_compare_not_supported:{a_flow}:{b_flow}")

    a_overrides = a_meta.get("applied_overrides") if isinstance(a_meta.get("applied_overrides"), dict) else {"prompt": {}, "config": {}, "contextual": {}}
    b_overrides = b_meta.get("applied_overrides") if isinstance(b_meta.get("applied_overrides"), dict) else {"prompt": {}, "config": {}, "contextual": {}}

    return {
        "a": _comparison_block(a),
        "b": _comparison_block(b),
        "relationship": {
            "a_is_experiment": bool(a_meta.get("used_overrides")),
            "b_is_experiment": bool(b_meta.get("used_overrides")),
            "experiment_kind": _experiment_kind(a_meta, b_meta),
            "same_optimizer_session": a_meta.get("optimizer_session_id") == b_meta.get("optimizer_session_id"),
            "a_optimizer_session": a_meta.get("optimizer_session_id"),
            "b_optimizer_session": b_meta.get("optimizer_session_id"),
        },
        "effective_overrides": {
            "a": a_overrides,
            "b": b_overrides,
            "category_differences": {
                "prompt": sorted(set(a_overrides.get("prompt", {}).keys()) ^ set(b_overrides.get("prompt", {}).keys())),
                "config": sorted(set(a_overrides.get("config", {}).keys()) ^ set(b_overrides.get("config", {}).keys())),
                "contextual": sorted(set(a_overrides.get("contextual", {}).keys()) ^ set(b_overrides.get("contextual", {}).keys())),
            },
        },
        "diff": {
            "final_status_changed": a.get("final_status") != b.get("final_status"),
            "latency_delta_ms": (b.get("total_latency_ms") or 0) - (a.get("total_latency_ms") or 0),
            "reply_changed": a.get("final_reply_text") != b.get("final_reply_text"),
            "guardrails": {
                "input_decision_changed": a.get("input_guardrail_decision") != b.get("input_guardrail_decision"),
                "output_decision_changed": a.get("output_guardrail_decision") != b.get("output_guardrail_decision"),
                "input_trigger_changed": a.get("input_guardrail_triggered") != b.get("input_guardrail_triggered"),
                "output_trigger_changed": a.get("output_guardrail_triggered") != b.get("output_guardrail_triggered"),
                "output_rewrite_changed": a.get("output_guardrail_rewrite_applied") != b.get("output_guardrail_rewrite_applied"),
                "output_enforcement_action_changed": a.get("output_guardrail_enforcement_action") != b.get("output_guardrail_enforcement_action"),
                "input_moderation_changed": a.get("input_moderation_used") != b.get("input_moderation_used"),
                "output_moderation_changed": a.get("output_moderation_used") != b.get("output_moderation_used"),
            },
            "node_changes": _node_diff(a, b),
            "prompt_artifact_changes": _prompt_artifact_diff(a, b),
        },
    }


def _comparison_block(turn: dict[str, Any]) -> dict[str, Any]:
    nodes = turn.get("nodes", {}) if isinstance(turn.get("nodes"), dict) else {}
    return {
        "turn_id": turn.get("turn_id"),
        "conversation_id": turn.get("conversation_id_after") or turn.get("conversation_id_before"),
        "final_reply": turn.get("final_reply_text"),
        "final_status": turn.get("final_status"),
        "latency_ms": turn.get("total_latency_ms"),
        "guardrails": {
            "input": turn.get("input_guardrail_decision"),
            "output": turn.get("output_guardrail_decision"),
            "input_triggered": turn.get("input_guardrail_triggered"),
            "output_triggered": turn.get("output_guardrail_triggered"),
            "output_rewrite": turn.get("output_guardrail_rewrite_applied"),
            "input_moderation_used": turn.get("input_moderation_used"),
            "output_moderation_used": turn.get("output_moderation_used"),
        },
        "fallback_or_error": [
            node_name
            for node_name, node in nodes.items()
            if isinstance(node, dict) and node.get("source") in {"fallback", "parse_error", "exception", "refusal"}
        ],
        "nodes": {
            node_name: {
                "status": node.get("status"),
                "source": node.get("source"),
                "latency_ms": node.get("latency_ms"),
            }
            for node_name, node in nodes.items()
            if isinstance(node, dict)
        },
        "optimizer": turn.get("_optimizador", {}),
    }


def _experiment_kind(a_meta: dict[str, Any], b_meta: dict[str, Any]) -> str:
    a_exp = bool(a_meta.get("used_overrides"))
    b_exp = bool(b_meta.get("used_overrides"))
    if not a_exp and b_exp:
        return "baseline_vs_experiment"
    if a_exp and not b_exp:
        return "experiment_vs_baseline"
    if a_exp and b_exp:
        return "experiment_vs_experiment"
    return "baseline_vs_baseline"


def _node_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, dict[str, Any]]:
    a_nodes = a.get("nodes", {}) if isinstance(a.get("nodes"), dict) else {}
    b_nodes = b.get("nodes", {}) if isinstance(b.get("nodes"), dict) else {}
    names = sorted(set(a_nodes.keys()) | set(b_nodes.keys()))
    diff: dict[str, dict[str, Any]] = {}
    for name in names:
        a_node = a_nodes.get(name, {}) if isinstance(a_nodes.get(name), dict) else {}
        b_node = b_nodes.get(name, {}) if isinstance(b_nodes.get(name), dict) else {}
        item = {
            "a_status": a_node.get("status"),
            "b_status": b_node.get("status"),
            "a_source": a_node.get("source"),
            "b_source": b_node.get("source"),
            "a_latency_ms": a_node.get("latency_ms"),
            "b_latency_ms": b_node.get("latency_ms"),
            "a_prompt_version": a_node.get("prompt_version"),
            "b_prompt_version": b_node.get("prompt_version"),
            "a_output_summary": a_node.get("output_summary"),
            "b_output_summary": b_node.get("output_summary"),
        }
        if any(item[k] != item[k.replace("a_", "b_")] for k in ["a_status", "a_source", "a_latency_ms", "a_prompt_version", "a_output_summary"]):
            diff[name] = item
    return diff


def _prompt_artifact_diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    a_nodes = a.get("nodes", {}) if isinstance(a.get("nodes"), dict) else {}
    b_nodes = b.get("nodes", {}) if isinstance(b.get("nodes"), dict) else {}
    names = sorted(set(a_nodes.keys()) | set(b_nodes.keys()))
    out: dict[str, Any] = {}
    for name in names:
        a_node = a_nodes.get(name, {}) if isinstance(a_nodes.get(name), dict) else {}
        b_node = b_nodes.get(name, {}) if isinstance(b_nodes.get(name), dict) else {}
        a_art = a_node.get("prompt_artifacts", {}) if isinstance(a_node.get("prompt_artifacts"), dict) else {}
        b_art = b_node.get("prompt_artifacts", {}) if isinstance(b_node.get("prompt_artifacts"), dict) else {}
        changed_fields = {
            "developer_prompt_text": a_art.get("developer_prompt_hash") != b_art.get("developer_prompt_hash"),
            "user_prompt_rendered": a_art.get("user_prompt_hash") != b_art.get("user_prompt_hash"),
            "input_payload_json": a_art.get("payload_hash") != b_art.get("payload_hash"),
            "prompt_version": a_art.get("prompt_version") != b_art.get("prompt_version"),
            "model_target": a_art.get("model_target") != b_art.get("model_target"),
            "threading_policy": a_art.get("threading_policy") != b_art.get("threading_policy"),
        }
        if any(changed_fields.values()):
            out[name] = {
                "changed": True,
                "fields": changed_fields,
                "a_hashes": {
                    "developer": a_art.get("developer_prompt_hash"),
                    "user": a_art.get("user_prompt_hash"),
                    "payload": a_art.get("payload_hash"),
                },
                "b_hashes": {
                    "developer": b_art.get("developer_prompt_hash"),
                    "user": b_art.get("user_prompt_hash"),
                    "payload": b_art.get("payload_hash"),
                },
            }
    return out
