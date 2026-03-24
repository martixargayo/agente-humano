from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from comunicacion.contexts import ensure_communication_session_context
from comunicacion.services.session_service import read_communication_runtime_refs, write_communication_runtime_refs
from comunicacion.storage import AttemptRecord, REPOSITORY
from sessions.state import get_session_store
from sessions.surface_scope import ensure_session_surface


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_attempt_id() -> str:
    return f'att_{uuid4().hex[:12]}'


def _get_existing_session_or_404(*, user_id: str, session_id: str):
    state = get_session_store().get(user_id=user_id, session_id=session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail={'error': 'session_not_found', 'user_id': user_id, 'session_id': session_id},
        )
    return state


def _assert_attempt_ownership(*, attempt: AttemptRecord, user_id: str, session_id: str) -> None:
    if attempt.user_id != user_id or attempt.session_id != session_id:
        raise HTTPException(
            status_code=404,
            detail={
                'error': 'attempt_not_found',
                'attempt_id': attempt.attempt_id,
                'user_id': user_id,
                'session_id': session_id,
            },
        )


def create_attempt(*, user_id: str, session_id: str) -> AttemptRecord:
    state = _get_existing_session_or_404(user_id=user_id, session_id=session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    bound_context = ensure_communication_session_context(state=state)
    now = _utcnow()
    attempt = AttemptRecord(
        attempt_id=_generate_attempt_id(),
        user_id=user_id,
        session_id=session_id,
        context_id=bound_context.context_id,
        status='draft',
        created_at=now,
        updated_at=now,
    )
    REPOSITORY.create_attempt(attempt)
    write_communication_runtime_refs(state=state, attempt_id=attempt.attempt_id, capture_status='draft')
    return attempt


def get_attempt(*, user_id: str, session_id: str, attempt_id: str) -> AttemptRecord:
    attempt = REPOSITORY.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(
            status_code=404,
            detail={'error': 'attempt_not_found', 'attempt_id': attempt_id},
        )
    _assert_attempt_ownership(attempt=attempt, user_id=user_id, session_id=session_id)
    state = _get_existing_session_or_404(user_id=user_id, session_id=session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    ensure_communication_session_context(state=state)
    return attempt
