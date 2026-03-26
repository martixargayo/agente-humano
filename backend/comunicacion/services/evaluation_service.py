from __future__ import annotations

from fastapi import HTTPException

from comunicacion.contexts import ensure_communication_session_context
from comunicacion.services.attempt_service import _get_existing_session_or_404
from comunicacion.services.session_service import read_communication_runtime_refs, write_communication_runtime_refs
from evaluacion.contracts.communication_models import CommunicationEvaluationStatusResponse, UiCommunicationReportV1
from evaluacion.engine.communication_service import (
    create_communication_evaluation,
    get_communication_evaluation_report,
    get_communication_evaluation_status,
)
from sessions.session_lock import SessionBusyError, acquire_session_execution_lock
from sessions.surface_scope import ensure_session_surface


def submit_attempt_for_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> CommunicationEvaluationStatusResponse:
    try:
        with acquire_session_execution_lock(user_id=user_id, session_id=session_id):
            state = _get_existing_session_or_404(user_id=user_id, session_id=session_id)
            ensure_session_surface(state=state, surface='comunicacion')
            ensure_communication_session_context(state=state)
            existing_refs = read_communication_runtime_refs(state)
            existing_eval_id = existing_refs.get('latest_evaluation_id')
            if existing_eval_id:
                try:
                    existing_status = get_communication_evaluation_status(evaluation_id=existing_eval_id)
                    if existing_status.attempt_id == attempt_id and existing_status.status in {'queued', 'running', 'completed'}:
                        return existing_status
                except HTTPException:
                    pass
            job = create_communication_evaluation(user_id=user_id, session_id=session_id, attempt_id=attempt_id)
            write_communication_runtime_refs(
                state=state,
                attempt_id=attempt_id,
                latest_evaluation_id=job.evaluation_id,
                capture_status='processing',
            )
            return job
    except SessionBusyError as exc:
        raise HTTPException(
            status_code=423,
            detail={
                'error': 'session_busy',
                'user_id': exc.user_id,
                'session_id': exc.session_id,
                'retry_after_seconds': exc.retry_after_seconds,
                'lock_backend': exc.lock_backend,
            },
            headers={'Retry-After': str(exc.retry_after_seconds)},
        ) from exc


def read_evaluation_status(*, evaluation_id: str) -> CommunicationEvaluationStatusResponse:
    return get_communication_evaluation_status(evaluation_id=evaluation_id)


def assert_evaluation_owner(*, evaluation_id: str, user_id: str, session_id: str) -> None:
    status = get_communication_evaluation_status(evaluation_id=evaluation_id)
    from comunicacion.storage import REPOSITORY
    attempt_record = REPOSITORY.get_attempt(status.attempt_id)
    if attempt_record is None or attempt_record.user_id != user_id or attempt_record.session_id != session_id:
        raise HTTPException(status_code=404, detail={'error': 'communication_evaluation_not_found'})


def read_evaluation_report(*, evaluation_id: str) -> UiCommunicationReportV1:
    report = get_communication_evaluation_report(evaluation_id=evaluation_id)
    return report
