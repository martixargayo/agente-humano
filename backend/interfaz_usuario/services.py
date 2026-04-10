from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

import logging
import secrets
import time

from fastapi import HTTPException

from sessions.lifecycle import (
    apply_session_ttl,
    mark_session_finalized,
    persist_session_with_ttl,
    touch_existing_session_if_present,
)
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
from conversacion_simple.contexts import (
    ConversationSimpleContextResolutionError,
    ConversationSimplePublicConflictError,
    ConversationSimplePublicSlugResolutionError,
    ensure_conversacion_simple_session_context,
    read_bound_conversacion_simple_context_from_session,
    resolve_conversacion_simple_context,
    resolve_conversacion_simple_public_context_selection,
)
from conversacion_simple.orchestration.flow_config import build_conversacion_simple_pipeline_config
from conversacion_simple.orchestration.pipeline import run_conversacion_simple_turn
from conversacion_simple.services import build_conversacion_simple_turn_context

from .presentation_resolver import resolve_presentation_config_for_context
from negociacion.orchestration.flow_config import build_negotiation_pipeline_config
from negociacion.orchestration.context_errors import ContextContractError
from negociacion.orchestration.turn_contract import TurnEntryContract, execute_turn_with_contract
from negociacion.optimizador.storage import resolve_traces
from negociacion.services.context_http import raise_http_from_context_error
from negociacion.services.turn_context_factory import build_interfaz_usuario_turn_context

logger = logging.getLogger(__name__)


def _resolve_flow_and_context_id(*, context_id: str | None, public_slug: str | None) -> tuple[str, str]:
    normalized_context_id = (context_id or "").strip() or None
    normalized_public_slug = (public_slug or "").strip() or None
    if normalized_context_id is None and normalized_public_slug is None:
        return "negociacion", _resolve_bootstrap_context_id(context_id=None, public_slug=None)
    if normalized_public_slug is not None:
        try:
            selection = resolve_public_context_selection(context_id=normalized_context_id, public_slug=normalized_public_slug)
            return "negociacion", selection.context_id
        except (PublicContextConflictError, PublicSlugResolutionError, NegotiationContextResolutionError):
            pass
        selection = resolve_conversacion_simple_public_context_selection(
            context_id=normalized_context_id,
            public_slug=normalized_public_slug,
        )
        return "conversacion_simple", selection.context_id

    assert normalized_context_id is not None
    try:
        resolved = resolve_negotiation_context(normalized_context_id)
        return resolved.flow_id, resolved.context_id
    except NegotiationContextResolutionError:
        resolved_cs = resolve_conversacion_simple_context(normalized_context_id)
        return resolved_cs.flow_id, resolved_cs.context_id


def _read_bound_surface_context(state: SessionState) -> tuple[str, str] | None:
    bound_neg = read_bound_context_from_session(state)
    bound_cs = read_bound_conversacion_simple_context_from_session(state)
    if bound_neg is not None and bound_cs is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "session_has_mixed_flow_bindings",
                "session_id": state.session_id,
                "negotiation_context_id": bound_neg.context_id,
                "conversacion_simple_context_id": bound_cs.context_id,
            },
        )
    if bound_neg is not None:
        return bound_neg.flow_id, bound_neg.context_id
    if bound_cs is not None:
        return bound_cs.flow_id, bound_cs.context_id
    return None


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


def _classify_exception(exc: Exception) -> dict[str, Any]:
    diagnostic = _diagnostic_from_exception(exc)
    normalized = diagnostic.lower()
    is_socket_write_timeout = "timeout writing to socket" in normalized or (
        "timeout" in normalized and "socket" in normalized and "write" in normalized
    )
    if is_socket_write_timeout:
        return {
            "diagnostic": diagnostic,
            "error_category": "upstream_write_timeout",
            "retryable": True,
        }
    return {
        "diagnostic": diagnostic,
        "error_category": "internal_turn_failure",
        "retryable": False,
    }


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
    try:
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
        bound_surface_context = _read_bound_surface_context(state)
        if bound_surface_context is not None:
            existing_flow_id, existing_context_id = bound_surface_context
            normalized_context_id = (context_id or "").strip() or None
            if normalized_context_id is not None and normalized_context_id != existing_context_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "session_context_conflict",
                        "existing_context_id": existing_context_id,
                        "requested_context_id": normalized_context_id,
                    },
                )
        requested_flow_id, requested_context_id = _resolve_flow_and_context_id(context_id=context_id, public_slug=public_slug)
        if bound_surface_context is not None:
            existing_flow_id, existing_context_id = bound_surface_context
            if existing_flow_id != requested_flow_id or existing_context_id != requested_context_id:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "session_context_conflict",
                        "existing_context_id": existing_context_id,
                        "requested_context_id": requested_context_id,
                    },
                )

        if requested_flow_id == "conversacion_simple":
            bound_cs = ensure_conversacion_simple_session_context(state=state, requested_context_id=requested_context_id)
            resolved_context = resolve_conversacion_simple_context(bound_cs.context_id)
            bound_context_id = bound_cs.context_id
        else:
            bound_neg = ensure_session_context(state=state, requested_context_id=requested_context_id)
            resolved_context = resolve_negotiation_context(bound_neg.context_id)
            bound_context_id = bound_neg.context_id
        presentation_config = resolve_presentation_config_for_context(bound_context_id)

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
    except ContextContractError as exc:
        raise_http_from_context_error(exc)
    except (ConversationSimpleContextResolutionError, ConversationSimplePublicConflictError) as exc:
        raise HTTPException(status_code=400, detail={"error": "bootstrap_context_input_conflict"}) from exc
    except ConversationSimplePublicSlugResolutionError as exc:
        raise HTTPException(status_code=404, detail={"error": "unsupported_public_slug", "public_slug": public_slug}) from exc


def create_new_conversation(*, user_id: str, base_session_id: str) -> dict[str, Any]:
    base_state = get_session_state(user_id=user_id, session_id=base_session_id)
    ensure_session_surface(state=base_state, surface='interfaz_usuario')
    base_bound = _read_bound_surface_context(base_state)
    if base_bound is None:
        bound_context = ensure_session_context(state=base_state)
        flow_id, context_id = bound_context.flow_id, bound_context.context_id
    else:
        flow_id, context_id = base_bound

    new_session_id = f"{base_session_id}__newconv__{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:6]}"
    new_state = SessionState(user_id=user_id, session_id=new_session_id)
    get_session_store().save(new_state)
    apply_session_ttl(new_state, scope="active", reason="interfaz_usuario_new_conversation")
    logger.info("interfaz_usuario_new_conversation_created source_session=%s new_session=%s", base_session_id, new_session_id)
    return ensure_session(user_id=user_id, session_id=new_session_id, context_id=context_id)


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
    turn_started = time.perf_counter()
    timing_ms: dict[str, int] = {}
    timing_precise_ms: dict[str, float] = {}

    def _mark(stage: str, started_at: float) -> None:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 3)
        timing_precise_ms[stage] = elapsed_ms
        timing_ms[stage] = int(elapsed_ms)

    post_commit_housekeeping_error: str | None = None
    resolved_flow_id: str | None = None
    try:
        with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
            touch_started = time.perf_counter()
            touch_ttl = touch_existing_session_if_present(
                user_id=user_id,
                session_id=session_id,
                scope="active",
                reason="interfaz_usuario_turn_lock_acquired",
            )
            _mark("touch_existing_session", touch_started)
            logger.info(
                "interfaz_usuario_turn_started session=%s new_conversation=%s ttl_seconds=%s",
                f"{user_id}:{session_id}",
                new_conversation,
                touch_ttl,
            )
            resolved_session_id = session_id
            auto_reset_applied = False
            # PERF: track whether we already hold a freshly-loaded state object
            # for the resolved session. This lets us skip a redundant Redis GET
            # in the hot path (previously ``load_base_state`` and
            # ``load_active_state`` both hit the same key when new_conversation
            # is False and no auto-reset happened, costing ~1 extra Redis RTT).
            base_state: SessionState | None = None
            base_state_session_id: str | None = None
            if new_conversation:
                new_conv_started = time.perf_counter()
                payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
                resolved_session_id = payload["session_id"]
                _mark("create_new_conversation", new_conv_started)
            else:
                load_base_started = time.perf_counter()
                base_state = get_session_state(user_id=user_id, session_id=session_id)
                base_state_session_id = session_id
                _mark("load_base_state", load_base_started)
                surface_guard_started = time.perf_counter()
                ensure_session_surface(state=base_state, surface='interfaz_usuario')
                _mark("ensure_surface_base_state", surface_guard_started)
                read_bound_started = time.perf_counter()
                base_bound_surface_context = _read_bound_surface_context(base_state)
                _mark("read_bound_surface_context_base", read_bound_started)
                if base_bound_surface_context is None:
                    ensure_ctx_started = time.perf_counter()
                    ensure_session_context(state=base_state)
                    _mark("ensure_session_context_legacy_backfill", ensure_ctx_started)
                    read_bound_after_started = time.perf_counter()
                    base_bound_surface_context = _read_bound_surface_context(base_state)
                    _mark("read_bound_surface_context_after_backfill", read_bound_after_started)
                is_negotiation_flow = isinstance(base_bound_surface_context, tuple) and base_bound_surface_context[0] == "negociacion"
                if is_negotiation_flow and _should_auto_reset_for_fresh_opener(state=base_state, message=message):
                    auto_new_conv_started = time.perf_counter()
                    payload = create_new_conversation(user_id=user_id, base_session_id=session_id)
                    resolved_session_id = payload["session_id"]
                    auto_reset_applied = True
                    _mark("auto_reset_create_new_conversation", auto_new_conv_started)

            load_active_started = time.perf_counter()
            if base_state is not None and base_state_session_id == resolved_session_id:
                # PERF: reuse the state already loaded above. ``base_state`` is
                # the same logical object Redis would return, so issuing a
                # second GET is pure overhead (~1 extra Redis RTT). Still
                # record the stage timing for observability continuity: it
                # will be near-zero, clearly signalling the optimization.
                state = base_state
            else:
                state = get_session_state(user_id=user_id, session_id=resolved_session_id)
            _mark("load_active_state", load_active_started)
            ensure_surface_active_started = time.perf_counter()
            ensure_session_surface(state=state, surface='interfaz_usuario')
            _mark("ensure_surface_active_state", ensure_surface_active_started)
            read_bound_active_started = time.perf_counter()
            bound_surface_context = _read_bound_surface_context(state)
            _mark("read_bound_surface_context_active", read_bound_active_started)
            if bound_surface_context is None:
                raise RuntimeError("session_context_required")
            flow_id, effective_context_id = bound_surface_context
            resolved_flow_id = flow_id
            if flow_id == "conversacion_simple":
                config_started = time.perf_counter()
                config = build_conversacion_simple_pipeline_config(context_id=effective_context_id, stateful=True)
                _mark("build_conversacion_simple_pipeline_config", config_started)
                turn_context_started = time.perf_counter()
                turn_context = build_conversacion_simple_turn_context(
                    state=state,
                    entrypoint="/api/interfaz_usuario/negociacion/turn",
                    entry_surface="interfaz_usuario",
                    context_source="interfaz_usuario_session_bound",
                    requested_context_id=effective_context_id,
                )
                _mark("build_conversacion_simple_turn_context", turn_context_started)
                pipeline_started = time.perf_counter()
                # PERF: skip the pipeline's internal save_session_state. The
                # atomic ``persist_session_with_ttl`` below handles both the
                # final save AND the TTL refresh in a single Redis round trip
                # (SET ... EX), replacing the previous pattern of
                # save_session_state (1 RTT) + apply_session_ttl -> save + touch
                # (2 more RTTs) with 1 RTT total. Lifecycle metadata is applied
                # in-memory before the save so it is included in the payload.
                reply, _, cs_meta = run_conversacion_simple_turn(
                    state=state,
                    user_message=message,
                    config=config,
                    turn_context=turn_context,
                    persist_state=False,
                )
                _mark("run_conversacion_simple_turn", pipeline_started)
                meta = {
                    "trace_count": len(resolve_traces(state)),
                    "latest_turn_id": cs_meta.get("turn_id"),
                    "entry_contract": {
                        "entry_surface": "interfaz_usuario",
                        "entrypoint": "/api/interfaz_usuario/negociacion/turn",
                        "overrides_applied": False,
                        "optimizer_wrapper_used": False,
                        "new_conversation": new_conversation,
                        "clone_used": False,
                        "config_snapshot": {
                            "memory_key": config.memory_key,
                            "flow_id": config.flow_id,
                            "context_id": config.context_id,
                            "brain_model_target": config.brain_model_target,
                            "summarizer_model_target": config.summarizer_model_target,
                            "brain_max_output_tokens": config.brain_max_output_tokens,
                            "context_limit_turns": config.context_limit_turns,
                            "keep_last_n_turns": config.keep_last_n_turns,
                            "recent_dialogue_short_max_messages": config.recent_dialogue_short_max_messages,
                            "episodic_compaction_trigger_count": config.episodic_compaction_trigger_count,
                            "episodic_compaction_trigger_chars": config.episodic_compaction_trigger_chars,
                            "max_episodic_high_resolution_items": config.max_episodic_high_resolution_items,
                            "maintenance_retry_limit": config.maintenance_retry_limit,
                            "compacted_summary_max_chars": config.compacted_summary_max_chars,
                            "maintenance_force_failure": config.maintenance_force_failure,
                        },
                    },
                    "context_meta": {
                        "flow_id": flow_id,
                        "context_id": effective_context_id,
                    },
                    "latency_pipeline_stage_timings_ms": cs_meta.get("stage_timings_ms"),
                    "latency_pipeline_stage_timings_precise_ms": cs_meta.get("stage_timings_precise_ms"),
                }
            else:
                bound_context = ensure_session_context(state=state, requested_context_id=effective_context_id)
                config = build_negotiation_pipeline_config(context_id=bound_context.context_id, stateful=True)
                turn_context = build_interfaz_usuario_turn_context(
                    state=state,
                    entrypoint="/api/interfaz_usuario/negociacion/turn",
                    requested_context_id=bound_context.context_id,
                )
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
                    turn_context=turn_context,
                )
            try:
                ttl_started = time.perf_counter()
                if flow_id == "conversacion_simple":
                    # PERF: single Redis round trip via SET ... EX. Combines
                    # what used to be pipeline-save (1 RTT) + save (1 RTT) +
                    # expire (1 RTT) = 3 RTTs into exactly 1.
                    persist_session_with_ttl(
                        state,
                        scope="active",
                        reason="interfaz_usuario_turn_completed",
                    )
                else:
                    apply_session_ttl(state, scope="active", reason="interfaz_usuario_turn_completed")
                _mark("apply_session_ttl_completed", ttl_started)
            except Exception as post_commit_exc:
                post_commit_housekeeping_error = _diagnostic_from_exception(post_commit_exc)
                logger.warning(
                    "interfaz_usuario_turn_post_commit_housekeeping_failed session=%s new_conversation=%s error=%s",
                    f"{user_id}:{resolved_session_id}",
                    new_conversation,
                    post_commit_housekeeping_error,
                )
                # CRITICAL: if the atomic persist path failed for
                # conversacion_simple, the state was never saved (because we
                # told the pipeline to skip its own save). Fall back to the
                # legacy apply_session_ttl path which performs a plain SAVE +
                # EXPIRE on independent round trips. This guarantees the turn
                # state is durably persisted even if the initial SETEX was
                # rejected for a reason unrelated to plain SET (e.g. a
                # transient Redis quirk with the EX argument path).
                if flow_id == "conversacion_simple":
                    try:
                        apply_session_ttl(state, scope="active", reason="interfaz_usuario_turn_completed_fallback")
                        post_commit_housekeeping_error = None
                        logger.warning(
                            "interfaz_usuario_turn_post_commit_housekeeping_recovered session=%s new_conversation=%s",
                            f"{user_id}:{resolved_session_id}",
                            new_conversation,
                        )
                    except Exception as fallback_exc:
                        post_commit_housekeeping_error = _diagnostic_from_exception(fallback_exc)
                        logger.warning(
                            "interfaz_usuario_turn_post_commit_housekeeping_fallback_failed session=%s error=%s",
                            f"{user_id}:{resolved_session_id}",
                            post_commit_housekeeping_error,
                        )
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
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, ContextContractError):
            raise_http_from_context_error(exc)
        error_id = f"iu_turn_{uuid4().hex[:10]}"
        classified = _classify_exception(exc)
        logger.exception(
            "interfaz_usuario_turn_failed error_id=%s session=%s message_len=%s new_conversation=%s cause=%s error_category=%s retryable=%s diagnostic=%s",
            error_id,
            f"{user_id}:{session_id}",
            len(message or ""),
            new_conversation,
            type(exc).__name__,
            classified["error_category"],
            classified["retryable"],
            classified["diagnostic"],
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": "turn_execution_failed",
                "error_id": error_id,
                "cause": type(exc).__name__,
                "diagnostic": classified["diagnostic"],
                "error_category": classified["error_category"],
                "retryable": classified["retryable"],
                "message": "No se pudo procesar el turno en este momento. Inténtalo de nuevo.",
            },
        ) from exc

    finish_button_armed = False
    if resolved_flow_id == "negociacion" and isinstance(state.world_state, dict):
        canonical = state.world_state.get("negotiation_canonical", {})
        ui_state = canonical.get("ui_state", {}) if isinstance(canonical, dict) else {}
        finish_button_armed = bool(ui_state.get("finish_button_armed", False)) if isinstance(ui_state, dict) else False
    elif resolved_flow_id == "conversacion_simple" and isinstance(state.world_state, dict):
        canonical = state.world_state.get("conversation_simple_canonical", {})
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
        "post_commit_housekeeping_error": post_commit_housekeeping_error,
        "latency_breakdown_ms": {
            "surface_stage_timings_ms": timing_ms,
            "surface_stage_timings_precise_ms": timing_precise_ms,
            "pipeline_stage_timings_ms": meta.get("latency_pipeline_stage_timings_ms") or {},
            "pipeline_stage_timings_precise_ms": meta.get("latency_pipeline_stage_timings_precise_ms") or {},
            "surface_total_ms": int((time.perf_counter() - turn_started) * 1000),
            "surface_total_precise_ms": round((time.perf_counter() - turn_started) * 1000, 3),
        },
    }
