from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from comunicacion.contexts import ensure_communication_session_context
from comunicacion.services.attempt_service import _assert_attempt_ownership, _get_existing_session_or_404
from comunicacion.services.session_service import write_communication_runtime_refs
from comunicacion.storage import AttemptNotFoundError, REPOSITORY, RecordingRecord
from sessions.surface_scope import ensure_session_surface


_ALLOWED_ATTACH_STATUSES = {'draft', 'uploaded'}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _generate_recording_id() -> str:
    return f'rec_{uuid4().hex[:12]}'


def attach_recording_to_attempt(
    *,
    user_id: str,
    session_id: str,
    attempt_id: str,
    mime_type: str,
    duration_ms: int,
    video_ref: str,
    poster_frame_ref: str | None = None,
    capture_meta: dict[str, Any] | None = None,
) -> RecordingRecord:
    state = _get_existing_session_or_404(user_id=user_id, session_id=session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    ensure_communication_session_context(state=state)

    normalized_mime_type = (mime_type or '').strip()
    normalized_video_ref = (video_ref or '').strip()
    if not normalized_mime_type:
        raise HTTPException(status_code=400, detail={'error': 'invalid_recording_metadata', 'field': 'mime_type'})
    if duration_ms <= 0:
        raise HTTPException(status_code=400, detail={'error': 'invalid_recording_metadata', 'field': 'duration_ms'})
    if not normalized_video_ref:
        raise HTTPException(status_code=400, detail={'error': 'invalid_recording_metadata', 'field': 'video_ref'})

    attempt = REPOSITORY.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail={'error': 'attempt_not_found', 'attempt_id': attempt_id})
    _assert_attempt_ownership(attempt=attempt, user_id=user_id, session_id=session_id)

    if attempt.status not in _ALLOWED_ATTACH_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'attempt_status_conflict',
                'attempt_id': attempt_id,
                'status': attempt.status,
            },
        )

    recording = RecordingRecord(
        recording_id=_generate_recording_id(),
        attempt_id=attempt.attempt_id,
        user_id=user_id,
        session_id=session_id,
        mime_type=normalized_mime_type,
        duration_ms=duration_ms,
        video_ref=normalized_video_ref,
        poster_frame_ref=(poster_frame_ref or '').strip() or None,
        capture_meta=dict(capture_meta or {}),
        created_at=_utcnow(),
    )
    try:
        REPOSITORY.attach_recording(recording)
    except AttemptNotFoundError as exc:
        raise HTTPException(status_code=404, detail={'error': 'attempt_not_found', 'attempt_id': attempt_id}) from exc

    updated_attempt = attempt.model_copy(update={
        'recording_id': recording.recording_id,
        'status': 'uploaded',
        'updated_at': _utcnow(),
    })
    REPOSITORY.save_attempt(updated_attempt)
    write_communication_runtime_refs(
        state=state,
        attempt_id=updated_attempt.attempt_id,
        recording_id=recording.recording_id,
        capture_status='uploaded',
    )
    return recording
