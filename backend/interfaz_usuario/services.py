from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

import logging
import secrets

from fastapi import HTTPException

from sessions.lifecycle import apply_session_ttl, mark_session_finalized, touch_existing_session_if_present
from sessions.session_lock import SessionBusyError, acquire_session_execution_lock
from sessions.state import SessionState, get_session_state, get_session_store
from sessions.surface_scope import ensure_session_surface

from negociacion.contexts import (
    NegotiationContextResolutionError,
    PublicContextConflictError,
    PublicSlugResolutionError,
    ensure_session_context,
    read_bound_context_from_session,
    resolve_public_context_selection,
    resolve_negotiation_context,
)

from .presentation_resolver import resolve_presentation_config_for_context
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.optimizador.storage import resolve_traces

logger = logging.getLogger(__name__)


def _resolve_bootstrap_context_id(*, context_id: str | None = None, public_slug: str | None = None) -> str:
    try:
        selection = resolve_public_context_selection(context_id=context_id, public_slug=public_slug)
    except PublicContextConflictError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "bootstrap_context_input_conflict",
                "context_id": (context_id or "").strip() or None,
                "public_slug": (public_slug or "").strip() or None,
            },
        ) from exc
    except PublicSlugResolutionError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unsupported_public_slug",
                "public_slug": (public_slug or "").strip() or None,
            },
        ) from exc
    except NegotiationContextResolutionError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unsupported_context_id",
                "context_id": (context_id or "").strip() or None,
            },
        ) from exc
    return selection.context_id


def _normalize_external_id(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value or None


def _generate_public_session_identity() -> tuple[str, str]:
    token = secrets.token_urlsafe(18)
    return f"iu_{token}", f"sess_{token}"


def ensure_session(
    *,
    user_id: str | None,
    session_id: str | None,
    context_id: str | None = None,
    public_slug: str | None = None,
) -> dict[str, Any]:
    normalized_user_id = _normalize_external_id(user_id)
    normalized_session_id = _normalize_external_id(session_id)
    if normalized_user_id is None or normalized_session_id is None:
        generated_user_id, generated_session_id = _generate_public_session_identity()
        normalized_user_id = normalized_user_id or generated_user_id
        normalized_session_id = normalized_session_id or generated_session_id

    store = get_session_store()
    existing_state = store.get(user_id=normalized_user_id, session_id=normalized_session_id)
    state = existing_state or get_session_state(user_id=normalized_user_id, session_id=normalized_session_id)
    ensure_session_surface(state=state, surface='interfaz_usuario')
    existing_context = read_bound_context_from_session(state)

    if existing_context is None:
        resolved_context_id = _resolve_bootstrap_context_id(context_id=context_id, public_slug=public_slug)
        ensure_session_context(state=state, requested_context_id=resolved_context_id)
    elif public_slug is not None:
        resolved_context_id = _resolve_bootstrap_context_id(context_id=context_id, public_slug=public_slug)
        ensure_session_context(state=state, requested_context_id=resolved_context_id)
    else:
        ensure_session_context(state=state, requested_context_id=context_id)

    bound_context = ensure_session_context(state=state)
    resolved_context = resolve_negotiation_context(bound_context.context_id)
    presentation_config = resolve_presentation_config_for_context(bound_context.context_id)

    traces = resolve_traces(state)
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    thread = canonical.get("openai_thread", {}) if isinstance(canonical, dict) else {}
    ttl_scope = "bootstrap" if existing_state is None and len(traces) == 0 else "active"
    session_bootstrap_state = "new" if existing_state is None and len(traces) == 0 else "rehydrated"
    ttl_seconds = apply_session_ttl(state, scope=ttl_scope, reason="interfaz_usuario_bootstrap")
    logger.info(
        "interfaz_usuario_session_ready session=%s context=%s traces=%s ttl_scope=%s ttl_seconds=%s existing=%s",
        f"{normalized_user_id}:{normalized_session_id}",
        resolved_context.context_id,
        len(traces),
        ttl_scope,
        ttl_seconds,
        existing_state is not None,
    )
    return {
        "user_id": normalized_user_id,
        "session_id": normalized_session_id,
        "trace_count": len(traces),
        "last_updated": state.last_updated.isoformat(),
        "session_bootstrap_state": session_bootstrap_state,
        "existing_session": existing_state is not None,
        "conversation_id": thread.get("conversation_id") if isinstance(thread, dict) else None,
        "previous_response_id": thread.get("previous_response_id") if isinstance(thread, dict) else None,
        "context_id": resolved_context.context_id,
        "public_slug": resolved_context.public_slug,
        "presentation_config": presentation_config.model_dump(mode="json"),
    }


def create_new_conversation(*, user_id: str, base_session_id: str) -> dict[str, Any]:
    base_state = get_session_state(user_id=user_id, session_id=base_session_id)
    ensure_session_surface(state=base_state, surface='interfaz_usuario')
    bound_context = ensure_session_context(state=base_state)

    new_session_id = f"{base_session_id}__newconv__{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:6]}"
    new_state = SessionState(user_id=user_id, session_id=new_session_id)
    get_session_store().save(new_state)
    apply_session_ttl(new_state, scope="active", reason="interfaz_usuario_new_conversation")
    logger.info("interfaz_usuario_new_conversation_created source_session=%s new_session=%s", base_session_id, new_session_id)
    return ensure_session(user_id=user_id, session_id=new_session_id, context_id=bound_context.context_id)


def finalize_session(*, user_id: str, session_id: str, reason: str | None = None) -> dict[str, Any]:
    finalize_reason = (reason or "").strip() or "interfaz_usuario_finalize"
    try:
        with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
            state = get_session_store().get(user_id=user_id, session_id=session_id)
            if state is None:
                raise HTTPException(status_code=404, detail={"error": "session_not_found", "user_id": user_id, "session_id": session_id})
            ensure_session_surface(state=state, surface='interfaz_usuario')
            ttl_seconds = mark_session_finalized(state, reason=finalize_reason)
            logger.info(
                "interfaz_usuario_session_finalized session=%s ttl_seconds=%s reason=%s",
                f"{user_id}:{session_id}",
                ttl_seconds,
                finalize_reason,
            )
            return {
                "user_id": user_id,
                "session_id": session_id,
                "status": "finalized",
                "ttl_seconds": ttl_seconds,
                "last_updated": state.last_updated.isoformat(),
            }
    except SessionBusyError as exc:
        logger.warning(
            "interfaz_usuario_finalize_busy session=%s retry_after=%s backend=%s",
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


def _should_auto_reset_for_fresh_opener(*, state: SessionState, message: str) -> bool:
    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    if not isinstance(canonical, dict):
        return False
    planner_state = canonical.get("planner_state", {})
    if not isinstance(planner_state, dict):
        return False

    phase = str(planner_state.get("current_phase") or "")
    if phase not in {"formalizacion_del_acuerdo", "abandono_de_la_negociacion"}:
        return False

    raw_recent = state.world_state.get("negotiation_canonical_recent_dialogue", []) if isinstance(state.world_state, dict) else []
    recent_len = len(raw_recent) if isinstance(raw_recent, list) else 0
    if recent_len < 4:
        return False

    normalized = " ".join(message.strip().lower().split())
    fresh_openers = ("hola", "buenas", "encantado", "buenos días", "buenas tardes")
    return normalized.startswith(fresh_openers)


def run_turn(*, user_id: str, session_id: str, message: str, new_conversation: bool = False) -> dict[str, Any]:
    try:
        with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
            touch_ttl = touch_existing_session_if_present(
                user_id=user_id,
                session_id=session_id,
                scope="active",
                reason="interfaz_usuario_turn_lock_acquired",
            )
            logger.info(
                "interfaz_usuario_turn_started session=%s new_conversation=%s ttl_seconds=%s",
                f"{user_id}:{session_id}",
                new_conversation,
                touch_ttl,
            )
            resolved_session_id = session_id
            auto_reset_applied = False
            if new_conversation:
                payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
                resolved_session_id = payload["session_id"]
            else:
                base_state = get_session_state(user_id=user_id, session_id=session_id)
                ensure_session_surface(state=base_state, surface='interfaz_usuario')
                ensure_session_context(state=base_state)
                if _should_auto_reset_for_fresh_opener(state=base_state, message=message):
                    payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
                    resolved_session_id = payload["session_id"]
                    auto_reset_applied = True

            state = get_session_state(user_id=user_id, session_id=resolved_session_id)
            ensure_session_surface(state=state, surface='interfaz_usuario')
            bound_context = ensure_session_context(state=state)
            apply_session_ttl(state, scope="active", reason="interfaz_usuario_turn_state_ready")
            config = build_negotiation_pipeline_config(context_id=bound_context.context_id)
            reply, _, meta = execute_turn_with_contract(
                state=state,
                user_message=message,
                config=config,
                contract=TurnEntryContract(
                    entry_surface="interfaz_usuario",
                    entrypoint="/api/interfaz_usuario/negociacion/turn",
                    overrides_applied=False,
                    optimizer_wrapper_used=False,
                    new_conversation=new_conversation,
                    clone_used=False,
                ),
            )
            apply_session_ttl(state, scope="active", reason="interfaz_usuario_turn_completed")
    except SessionBusyError as exc:
        touch_existing_session_if_present(
            user_id=exc.user_id,
            session_id=exc.session_id,
            scope="active",
            reason="interfaz_usuario_turn_busy",
        )
        logger.warning(
            "interfaz_usuario_turn_busy session=%s retry_after=%s backend=%s",
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

    canonical = state.world_state.get("negotiation_canonical", {}) if isinstance(state.world_state, dict) else {}
    ui_state = canonical.get("ui_state", {}) if isinstance(canonical, dict) else {}
    finish_button_armed = bool(ui_state.get("finish_button_armed", False)) if isinstance(ui_state, dict) else False

    return {
        "reply": reply,
        "user_id": user_id,
        "session_id": resolved_session_id,
        "trace_count": meta.get("trace_count", 0),
        "conversation_id_before": meta.get("conversation_id_before"),
        "conversation_id_after": meta.get("conversation_id_after"),
        "previous_response_id_before": meta.get("previous_response_id_before"),
        "previous_response_id_after": meta.get("previous_response_id_after"),
        "latest_turn_id": meta.get("latest_turn_id"),
        "entry_contract": meta.get("entry_contract") or {},
        "auto_reset_applied": auto_reset_applied,
        "finish_button_armed": finish_button_armed,
    }
