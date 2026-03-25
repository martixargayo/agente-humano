from __future__ import annotations

from fastapi import APIRouter, Query

from comunicacion.models import (
    CommunicationEvaluationReportResponse,
    CommunicationEvaluationStatusApiResponse,
    CommunicationSessionBootstrapRequest,
    CommunicationSessionBootstrapResponse,
    CreateAttemptRequest,
    CreateAttemptResponse,
    GetAttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    UploadRecordingRequest,
    UploadRecordingResponse,
)
from comunicacion.services import (
    attach_recording_to_attempt,
    create_attempt,
    ensure_communication_session,
    get_attempt,
    read_evaluation_report,
    read_evaluation_status,
    submit_attempt_for_evaluation,
)
from comunicacion.storage import REPOSITORY

router = APIRouter(prefix='/api/comunicacion', tags=['comunicacion'])


@router.post('/sessions/bootstrap', response_model=CommunicationSessionBootstrapResponse)
def bootstrap_session(payload: CommunicationSessionBootstrapRequest) -> CommunicationSessionBootstrapResponse:
    return CommunicationSessionBootstrapResponse(
        **ensure_communication_session(
            user_id=payload.user_id,
            session_id=payload.session_id,
            context_id=payload.context_id,
            public_slug=payload.public_slug,
        )
    )


@router.post('/attempts', response_model=CreateAttemptResponse)
def create_attempt_endpoint(payload: CreateAttemptRequest) -> CreateAttemptResponse:
    attempt = create_attempt(user_id=payload.user_id, session_id=payload.session_id)
    return CreateAttemptResponse(
        attempt_id=attempt.attempt_id,
        status=attempt.status,
        context_id=attempt.context_id,
        recording_id=attempt.recording_id,
        latest_evaluation_id=attempt.latest_evaluation_id,
        rerecord_count=attempt.rerecord_count,
    )


@router.get('/attempts/{attempt_id}', response_model=GetAttemptResponse)
def get_attempt_endpoint(
    attempt_id: str,
    *,
    user_id: str = Query(...),
    session_id: str = Query(...),
) -> GetAttemptResponse:
    attempt = get_attempt(user_id=user_id, session_id=session_id, attempt_id=attempt_id)
    return GetAttemptResponse(
        attempt_id=attempt.attempt_id,
        status=attempt.status,
        context_id=attempt.context_id,
        recording_id=attempt.recording_id,
        latest_evaluation_id=attempt.latest_evaluation_id,
        rerecord_count=attempt.rerecord_count,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


@router.post('/attempts/{attempt_id}/upload', response_model=UploadRecordingResponse)
def attach_recording_endpoint(attempt_id: str, payload: UploadRecordingRequest) -> UploadRecordingResponse:
    recording = attach_recording_to_attempt(
        user_id=payload.user_id,
        session_id=payload.session_id,
        attempt_id=attempt_id,
        mime_type=payload.mime_type,
        duration_ms=payload.duration_ms,
        video_ref=payload.video_ref,
        poster_frame_ref=payload.poster_frame_ref,
        capture_meta=payload.capture_meta,
    )
    attempt = REPOSITORY.get_attempt(attempt_id)
    status = attempt.status if attempt is not None else 'uploaded'
    return UploadRecordingResponse(
        attempt_id=attempt_id,
        recording_id=recording.recording_id,
        status=status,
        video_ref=recording.video_ref,
        poster_frame_ref=recording.poster_frame_ref,
    )


@router.post('/attempts/{attempt_id}/submit', response_model=SubmitAttemptResponse)
def submit_attempt_endpoint(attempt_id: str, payload: SubmitAttemptRequest) -> SubmitAttemptResponse:
    status = submit_attempt_for_evaluation(
        user_id=payload.user_id,
        session_id=payload.session_id,
        attempt_id=attempt_id,
    )
    return SubmitAttemptResponse(
        attempt_id=status.attempt_id,
        evaluation_id=status.evaluation_id,
        status=status.status,
    )


@router.get('/evaluations/{evaluation_id}', response_model=CommunicationEvaluationStatusApiResponse)
def get_evaluation_status_endpoint(evaluation_id: str) -> CommunicationEvaluationStatusApiResponse:
    return CommunicationEvaluationStatusApiResponse(**read_evaluation_status(evaluation_id=evaluation_id).model_dump())


@router.get('/evaluations/{evaluation_id}/report', response_model=CommunicationEvaluationReportResponse)
def get_evaluation_report_endpoint(evaluation_id: str) -> CommunicationEvaluationReportResponse:
    return CommunicationEvaluationReportResponse(**read_evaluation_report(evaluation_id=evaluation_id).model_dump())
