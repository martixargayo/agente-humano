from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

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
from comunicacion.services.recording_service import (
    build_recording_playback_url,
    persist_uploaded_video_blob,
    resolve_recording_playback_path,
)
from comunicacion.storage import REPOSITORY

router = APIRouter(prefix='/api/comunicacion', tags=['comunicacion'])


def _parse_capture_meta(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail={'error': 'invalid_capture_meta_json'}) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail={'error': 'invalid_capture_meta_json'})
    return parsed


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
async def attach_recording_endpoint(attempt_id: str, request: Request) -> UploadRecordingResponse:
    content_type = (request.headers.get('content-type') or '').lower()
    if 'multipart/form-data' in content_type:
        form = await request.form()
        user_id = str(form.get('user_id') or '').strip()
        session_id = str(form.get('session_id') or '').strip()
        mime_type = str(form.get('mime_type') or '').strip() or 'video/webm'
        try:
            duration_ms = int(str(form.get('duration_ms') or '0'))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail={'error': 'invalid_recording_metadata', 'field': 'duration_ms'}) from exc
        poster_frame_ref = str(form.get('poster_frame_ref') or '').strip() or None
        capture_meta = _parse_capture_meta(str(form.get('capture_meta') or '').strip() or None)

        upload_file = form.get('video_file')
        if upload_file is None:
            raise HTTPException(status_code=400, detail={'error': 'recording_media_file_missing'})
        media_bytes = await upload_file.read()
        video_ref = persist_uploaded_video_blob(
            attempt_id=attempt_id,
            original_filename=getattr(upload_file, 'filename', None),
            payload=media_bytes,
            mime_type_hint=getattr(upload_file, 'content_type', None) or mime_type,
        )
        capture_meta = dict(capture_meta)
        capture_meta.update({
            'blob_size_bytes': len(media_bytes),
            'uploaded_binary': True,
            'upload_transport': 'multipart_form_data',
        })
        payload = UploadRecordingRequest(
            user_id=user_id,
            session_id=session_id,
            mime_type=mime_type,
            duration_ms=duration_ms,
            video_ref=video_ref,
            poster_frame_ref=poster_frame_ref,
            capture_meta=capture_meta,
        )
    else:
        payload = UploadRecordingRequest.model_validate(await request.json())

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
        playback_url=build_recording_playback_url(recording_id=recording.recording_id, video_ref=recording.video_ref),
        poster_frame_ref=recording.poster_frame_ref,
    )


@router.get('/recordings/{recording_id}/video')
def stream_recording_video_endpoint(recording_id: str) -> FileResponse:
    recording = REPOSITORY.get_recording(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail={'error': 'recording_not_found', 'recording_id': recording_id})
    parsed_path = resolve_recording_playback_path(video_ref=recording.video_ref)
    extension = 'mp4' if (recording.mime_type or '').lower().startswith('video/mp4') else 'webm'
    return FileResponse(path=parsed_path, media_type=recording.mime_type, filename=f'{recording_id}.{extension}')


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
