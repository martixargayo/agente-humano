from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from sessions.lifecycle import apply_session_ttl
from sessions.state import get_session_state, get_session_store
from sessions.surface_scope import ensure_session_surface

from comunicacion.contexts import (
    CommunicationContextResolutionError,
    PublicContextConflictError,
    PublicSlugResolutionError,
    ensure_communication_session_context,
    read_bound_communication_context_from_session,
    resolve_communication_context,
    resolve_public_communication_selection,
)

logger = logging.getLogger(__name__)

COMMUNICATION_RUNTIME_WORLD_STATE_KEY = 'communication_runtime'


def _ensure_communication_runtime_block(state) -> dict[str, Any]:
    if not isinstance(state.world_state, dict):
        state.world_state = {}
    raw = state.world_state.get(COMMUNICATION_RUNTIME_WORLD_STATE_KEY)
    if not isinstance(raw, dict):
        raw = {}
        state.world_state[COMMUNICATION_RUNTIME_WORLD_STATE_KEY] = raw
    return raw


def read_communication_runtime_refs(state) -> dict[str, Any]:
    runtime = _ensure_communication_runtime_block(state)
    return {
        'active_attempt_id': runtime.get('active_attempt_id'),
        'last_recording_id': runtime.get('last_recording_id'),
        'latest_evaluation_id': runtime.get('latest_evaluation_id'),
        'capture_status': runtime.get('capture_status'),
    }


def write_communication_runtime_refs(
    *,
    state,
    attempt_id: str | None = None,
    recording_id: str | None = None,
    latest_evaluation_id: str | None = None,
    capture_status: str | None = None,
) -> dict[str, Any]:
    runtime = _ensure_communication_runtime_block(state)
    if attempt_id is not None:
        runtime['active_attempt_id'] = attempt_id
    if recording_id is not None:
        runtime['last_recording_id'] = recording_id
    if latest_evaluation_id is not None:
        runtime['latest_evaluation_id'] = latest_evaluation_id
    if capture_status is not None:
        runtime['capture_status'] = capture_status
    return runtime


def _normalize_external_id(raw: str | None) -> str | None:
    value = (raw or '').strip()
    return value or None


def _generate_public_session_identity() -> tuple[str, str]:
    token = secrets.token_urlsafe(18)
    return f'iu_{token}', f'sess_{token}'


def _resolve_bootstrap_context_id(*, context_id: str | None = None, public_slug: str | None = None) -> str:
    try:
        selection = resolve_public_communication_selection(context_id=context_id, public_slug=public_slug)
    except PublicContextConflictError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                'error': 'bootstrap_context_input_conflict',
                'context_id': (context_id or '').strip() or None,
                'public_slug': (public_slug or '').strip() or None,
            },
        ) from exc
    except PublicSlugResolutionError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                'error': 'unsupported_public_slug',
                'public_slug': (public_slug or '').strip() or None,
            },
        ) from exc
    except CommunicationContextResolutionError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                'error': 'unsupported_context_id',
                'context_id': (context_id or '').strip() or None,
            },
        ) from exc
    return selection.context_id


def _load_json_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise RuntimeError(f'invalid_json_object:{path}')
    return payload


def ensure_communication_session(
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
    ensure_session_surface(state=state, surface='comunicacion')

    existing_context = read_bound_communication_context_from_session(state)
    if existing_context is None or public_slug is not None:
        resolved_context_id = _resolve_bootstrap_context_id(context_id=context_id, public_slug=public_slug)
        ensure_communication_session_context(state=state, requested_context_id=resolved_context_id)
    else:
        ensure_communication_session_context(state=state, requested_context_id=context_id)

    bound_context = ensure_communication_session_context(state=state)
    resolved_context = resolve_communication_context(bound_context.context_id)
    presentation_config = _load_json_file(resolved_context.presentation_dir / 'presentation_config.json')
    activity_brief = _load_json_file(resolved_context.assets_dir / 'activity_brief.json')
    capture_policy = _load_json_file(resolved_context.assets_dir / 'capture_policy.json')

    runtime_refs = read_communication_runtime_refs(state)
    ttl_scope = 'bootstrap' if existing_state is None else 'active'
    apply_session_ttl(state, scope=ttl_scope, reason='comunicacion_bootstrap')
    logger.info(
        'comunicacion_session_ready session=%s context=%s ttl_scope=%s existing=%s',
        f'{normalized_user_id}:{normalized_session_id}',
        resolved_context.context_id,
        ttl_scope,
        existing_state is not None,
    )
    return {
        'user_id': normalized_user_id,
        'session_id': normalized_session_id,
        'session_bootstrap_state': 'new' if existing_state is None else 'rehydrated',
        'existing_session': existing_state is not None,
        'context_id': resolved_context.context_id,
        'public_slug': resolved_context.public_slug,
        'presentation_config': presentation_config,
        'activity_brief': activity_brief,
        'capture_policy': capture_policy,
        'trace_count': 0,
        'last_updated': state.last_updated.isoformat(),
        'communication_status': runtime_refs.get('capture_status') or 'bootstrap_ready',
        'last_attempt_id': runtime_refs.get('active_attempt_id'),
        'last_evaluation_id': runtime_refs.get('latest_evaluation_id'),
        'extras': {},
    }
