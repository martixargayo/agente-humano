from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Literal

from .state import SessionState, get_session_store, save_session_state

logger = logging.getLogger(__name__)

SESSION_LIFECYCLE_WORLD_STATE_KEY = "_session_lifecycle"
SessionTtlScope = Literal["bootstrap", "active", "finalized"]


def _is_socket_timeout_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "timeout" in text and "socket" in text


def _ttl_from_env(name: str, default: int) -> int:
    return max(1, int(os.getenv(name, str(default))))


def bootstrap_session_ttl_seconds() -> int:
    return _ttl_from_env("SESSION_BOOTSTRAP_TTL_SECONDS", 1800)


def active_session_ttl_seconds() -> int:
    return _ttl_from_env("SESSION_ACTIVE_TTL_SECONDS", 43200)


def finalized_session_ttl_seconds() -> int:
    return _ttl_from_env("SESSION_FINALIZED_TTL_SECONDS", 600)


def resolve_session_ttl(scope: SessionTtlScope) -> int:
    if scope == "bootstrap":
        return bootstrap_session_ttl_seconds()
    if scope == "finalized":
        return finalized_session_ttl_seconds()
    return active_session_ttl_seconds()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_lifecycle_block(state: SessionState) -> dict[str, Any]:
    raw = state.world_state.get(SESSION_LIFECYCLE_WORLD_STATE_KEY, {}) if isinstance(state.world_state, dict) else {}
    if not isinstance(raw, dict):
        raw = {}
    state.world_state[SESSION_LIFECYCLE_WORLD_STATE_KEY] = raw
    return raw


def apply_session_ttl(
    state: SessionState,
    *,
    scope: SessionTtlScope,
    reason: str,
    persist: bool = True,
) -> int:
    ttl_seconds = resolve_session_ttl(scope)
    now_iso = _now_iso()
    lifecycle = _ensure_lifecycle_block(state)
    lifecycle.setdefault("created_at", now_iso)
    lifecycle["status"] = "finalized" if scope == "finalized" else "active"
    lifecycle["ttl_scope"] = scope
    lifecycle["ttl_seconds"] = ttl_seconds
    lifecycle["last_touched_at"] = now_iso
    lifecycle["last_reason"] = reason
    if scope == "finalized":
        lifecycle["finalized_at"] = now_iso
    elif "finalized_at" in lifecycle:
        lifecycle.pop("finalized_at", None)

    if persist:
        save_session_state(state)
    get_session_store().touch(user_id=state.user_id, session_id=state.session_id, ttl_seconds=ttl_seconds)
    logger.info(
        "session_ttl_applied session=%s scope=%s ttl_seconds=%s reason=%s persist=%s",
        f"{state.user_id}:{state.session_id}",
        scope,
        ttl_seconds,
        reason,
        persist,
    )
    return ttl_seconds


def touch_existing_session_if_present(
    *,
    user_id: str,
    session_id: str,
    scope: SessionTtlScope,
    reason: str,
) -> int | None:
    ttl_seconds = resolve_session_ttl(scope)
    try:
        # Ruta ligera: refrescar TTL sin lecturas/escrituras adicionales de estado.
        # Evita I/O redundante (GET + SAVE + EXPIRE) en puntos de alta frecuencia
        # como "*_turn_lock_acquired".
        get_session_store().touch(user_id=user_id, session_id=session_id, ttl_seconds=ttl_seconds)
        logger.info(
            "session_ttl_touch_applied_lightweight session=%s scope=%s ttl_seconds=%s reason=%s",
            f"{user_id}:{session_id}",
            scope,
            ttl_seconds,
            reason,
        )
        return ttl_seconds
    except Exception as exc:
        if _is_socket_timeout_error(exc):
            # No degradar a camino pesado ante timeout de socket: eso añade GET+SAVE
            # y aumenta presión sobre la misma dependencia degradada.
            raise
        state = get_session_store().get(user_id=user_id, session_id=session_id)
        if state is None:
            logger.info(
                "session_ttl_touch_skipped_missing session=%s scope=%s reason=%s",
                f"{user_id}:{session_id}",
                scope,
                reason,
            )
            return None
        return apply_session_ttl(state, scope=scope, reason=reason, persist=True)


def mark_session_finalized(state: SessionState, *, reason: str) -> int:
    return apply_session_ttl(state, scope="finalized", reason=reason, persist=True)
