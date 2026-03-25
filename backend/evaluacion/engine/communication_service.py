from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from comunicacion.storage import REPOSITORY
from comunicacion.storage.models import AttemptRecord, DerivedArtifactRecord
from evaluacion.contracts.communication_models import (
    CommunicationEvaluationStatusResponse,
    UiCommunicationReportV1,
)
from evaluacion.engine.communication_bundle_builder import build_communication_feedback_input_bundle
from evaluacion.engine.communication_evaluators import (
    evaluate_communication_content,
    evaluate_communication_delivery,
    evaluate_communication_visual_placeholder,
)
from evaluacion.engine.communication_report_assembler import assemble_communication_report

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix='communication_eval')
_LAUNCH_LOCK = threading.Lock()

_STAGE_SEQUENCE = [
    'queued',
    'extracting',
    'extracting_media',
    'transcription_started',
    'transcript_ready',
    'content_analysis_ready',
    'audio_features_ready',
    'visual_placeholder_ready',
    'assembling_report',
    'completed',
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _utcnow().isoformat()


def _generate_evaluation_id() -> str:
    return f'eval_{uuid4().hex[:12]}'


def _generate_artifact_id() -> str:
    return f'art_{uuid4().hex[:12]}'


def _jobs_block() -> dict[str, object]:
    if not hasattr(REPOSITORY, '_communication_eval_jobs'):
        REPOSITORY._communication_eval_jobs = {}
    return REPOSITORY._communication_eval_jobs


def _reports_block() -> dict[str, object]:
    if not hasattr(REPOSITORY, '_communication_eval_reports'):
        REPOSITORY._communication_eval_reports = {}
    return REPOSITORY._communication_eval_reports


def _set_job(*, evaluation_id: str, attempt_id: str, status: str, stage: str, error: str | None = None) -> dict[str, object]:
    jobs = _jobs_block()
    existing = dict(jobs.get(evaluation_id, {}))
    existing.update({
        'evaluation_id': evaluation_id,
        'attempt_id': attempt_id,
        'status': status,
        'stage': stage,
        'report_available': bool(_reports_block().get(evaluation_id)),
        'error': error,
        'updated_at': _iso(),
    })
    existing.setdefault('created_at', existing['updated_at'])
    jobs[evaluation_id] = existing
    return existing


def _get_attempt_or_404(*, attempt_id: str) -> AttemptRecord:
    attempt = REPOSITORY.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail={'error': 'attempt_not_found', 'attempt_id': attempt_id})
    return attempt


def _validate_attempt_owner(*, attempt: AttemptRecord, user_id: str, session_id: str) -> None:
    if attempt.user_id != user_id or attempt.session_id != session_id:
        raise HTTPException(
            status_code=404,
            detail={'error': 'attempt_not_found', 'attempt_id': attempt.attempt_id, 'user_id': user_id, 'session_id': session_id},
        )


def _run_communication_evaluation_job(*, evaluation_id: str, attempt_id: str) -> None:
    try:
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='extracting')
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='extracting_media')
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='transcription_started')
        bundle = build_communication_feedback_input_bundle(evaluation_id=evaluation_id, attempt_id=attempt_id)

        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='transcript_ready')
        if getattr(bundle.transcript, 'status', None) == 'ready':
            persist_transcript_artifact(evaluation_id=evaluation_id, bundle=bundle)
        content_result = evaluate_communication_content(bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='content_analysis_ready')
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='audio_features_ready')
        visual_result = evaluate_communication_visual_placeholder(bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='visual_placeholder_ready')
        delivery_result = evaluate_communication_delivery(bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='assembling_report')

        report = assemble_communication_report(
            bundle=bundle,
            content_output=content_result,
            delivery_output=delivery_result,
            visual_output=visual_result,
        )
        _reports_block()[evaluation_id] = report
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='completed', stage='completed')

        attempt = _get_attempt_or_404(attempt_id=attempt_id)
        REPOSITORY.save_attempt(attempt.model_copy(update={
            'status': 'completed',
            'latest_evaluation_id': evaluation_id,
            'updated_at': _utcnow(),
        }))
    except Exception as exc:  # pragma: no cover
        attempt = REPOSITORY.get_attempt(attempt_id)
        if attempt is not None:
            REPOSITORY.save_attempt(attempt.model_copy(update={'status': 'failed', 'updated_at': _utcnow()}))
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='failed', stage='failed', error=f'pipeline_error:{type(exc).__name__}:{exc}')


def persist_transcript_artifact(*, evaluation_id: str, bundle: object) -> None:
    transcript = getattr(bundle, 'transcript', None)
    recording = getattr(bundle, 'recording', None)
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if transcript is None or recording is None or attempt_ref is None:
        return
    if getattr(transcript, 'status', None) != 'ready':
        return
    storage_ref = f'memory://communication/transcript/{evaluation_id}/{getattr(attempt_ref, "recording_id", "unknown")}.json'
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='transcript_real',
            version=getattr(transcript, 'schema_version', 'communication_transcript_real.v1'),
            storage_ref=storage_ref,
            content_hash=None,
            created_at=_utcnow(),
        )
    )


def create_communication_evaluation(*, user_id: str, session_id: str, attempt_id: str) -> CommunicationEvaluationStatusResponse:
    attempt = _get_attempt_or_404(attempt_id=attempt_id)
    _validate_attempt_owner(attempt=attempt, user_id=user_id, session_id=session_id)
    if not attempt.recording_id:
        raise HTTPException(status_code=409, detail={'error': 'attempt_recording_required', 'attempt_id': attempt_id})

    evaluation_id = _generate_evaluation_id()
    REPOSITORY.save_attempt(attempt.model_copy(update={
        'status': 'submitted',
        'latest_evaluation_id': evaluation_id,
        'submitted_at': _utcnow(),
        'updated_at': _utcnow(),
    }))
    _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='queued', stage='queued')
    with _LAUNCH_LOCK:
        _EXECUTOR.submit(_run_communication_evaluation_job, evaluation_id=evaluation_id, attempt_id=attempt_id)
    return get_communication_evaluation_status(evaluation_id=evaluation_id)


def get_communication_evaluation_status(*, evaluation_id: str) -> CommunicationEvaluationStatusResponse:
    job = _jobs_block().get(evaluation_id)
    if not isinstance(job, dict):
        raise HTTPException(status_code=404, detail='communication_evaluation_not_found')
    return CommunicationEvaluationStatusResponse(
        evaluation_id=str(job['evaluation_id']),
        attempt_id=str(job['attempt_id']),
        status=str(job['status']),
        stage=str(job['stage']),
        report_available=bool(_reports_block().get(evaluation_id)),
        error=job.get('error'),
    )


def get_communication_evaluation_report(*, evaluation_id: str) -> UiCommunicationReportV1:
    status = get_communication_evaluation_status(evaluation_id=evaluation_id)
    if status.status != 'completed':
        raise HTTPException(status_code=409, detail=f'communication_evaluation_not_completed:{status.status}')
    report = _reports_block().get(evaluation_id)
    if not isinstance(report, UiCommunicationReportV1):
        raise HTTPException(status_code=404, detail='communication_evaluation_report_not_found')
    return report


def run_communication_evaluation_job_inline_for_tests(*, evaluation_id: str, attempt_id: str) -> None:
    _run_communication_evaluation_job(evaluation_id=evaluation_id, attempt_id=attempt_id)


def list_communication_job_stages() -> list[str]:
    return list(_STAGE_SEQUENCE)
