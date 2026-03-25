from __future__ import annotations

from fastapi import HTTPException

from comunicacion.contexts import ensure_communication_session_context
from comunicacion.services.attempt_service import _get_existing_session_or_404
from comunicacion.services.session_service import write_communication_runtime_refs
from evaluacion.contracts.communication_models import CommunicationEvaluationStatusResponse, UiCommunicationReportV1
from evaluacion.engine.communication_service import (
    create_communication_evaluation,
    get_communication_evaluation_report,
    get_communication_evaluation_status,
)
from sessions.surface_scope import ensure_session_surface


def submit_attempt_for_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> CommunicationEvaluationStatusResponse:
    state = _get_existing_session_or_404(user_id=user_id, session_id=session_id)
    ensure_session_surface(state=state, surface='comunicacion')
    ensure_communication_session_context(state=state)
    job = create_communication_evaluation(user_id=user_id, session_id=session_id, attempt_id=attempt_id)
    write_communication_runtime_refs(
        state=state,
        attempt_id=attempt_id,
        latest_evaluation_id=job.evaluation_id,
        capture_status='processing',
    )
    return job


def read_evaluation_status(*, evaluation_id: str) -> CommunicationEvaluationStatusResponse:
    return get_communication_evaluation_status(evaluation_id=evaluation_id)


def read_evaluation_report(*, evaluation_id: str) -> UiCommunicationReportV1:
    report = get_communication_evaluation_report(evaluation_id=evaluation_id)
    return report
