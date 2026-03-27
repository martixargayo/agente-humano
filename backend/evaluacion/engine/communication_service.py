from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError, as_completed
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
    evaluate_communication_synthesis,
    evaluate_communication_visual,
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
    'content_analysis_started',
    'content_analysis_ready',
    'delivery_analysis_started',
    'audio_metrics_started',
    'audio_features_ready',
    'delivery_analysis_ready',
    'frame_extraction_started',
    'frames_ready',
    'visual_analysis_started',
    'visual_analysis_ready',
    'synthesis_started',
    'synthesis_ready',
    'assembling_report',
    'completed',
]
_PARALLEL_ANALYSIS_TIMEOUT_SECONDS = 45.0


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
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='audio_metrics_started')
        if getattr(bundle.audio_features, 'status', None) == 'ready':
            persist_audio_metrics_artifact(evaluation_id=evaluation_id, bundle=bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='audio_features_ready')
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='frame_extraction_started')
        if getattr(bundle.visual_features, 'status', None) == 'ready':
            persist_frame_manifest_artifact(evaluation_id=evaluation_id, bundle=bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='frames_ready')
        content_result, delivery_result, visual_result, branch_errors = _run_parallel_communication_analyses(
            evaluation_id=evaluation_id,
            attempt_id=attempt_id,
            bundle=bundle,
        )
        if branch_errors:
            merged_error = ';'.join(f'{name}:{error}' for name, error in sorted(branch_errors.items()))
            _set_job(
                evaluation_id=evaluation_id,
                attempt_id=attempt_id,
                status='running',
                stage='visual_analysis_ready',
                error=f'partial_failures:{merged_error}',
            )
        persist_visual_batch_eval_artifacts(evaluation_id=evaluation_id, bundle=bundle, visual_output=visual_result)
        persist_visual_llm_final_artifact(evaluation_id=evaluation_id, bundle=bundle, visual_output=visual_result)
        persist_visual_evaluation_artifact(evaluation_id=evaluation_id, bundle=bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='synthesis_started')
        synthesis_result, synthesis_meta = evaluate_communication_synthesis(
            bundle=bundle,
            content_output=content_result,
            delivery_output=delivery_result,
            visual_output=visual_result,
        )
        persist_global_synthesis_artifact(evaluation_id=evaluation_id, bundle=bundle)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='synthesis_ready')
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage='assembling_report')

        report = assemble_communication_report(
            bundle=bundle,
            content_output=content_result,
            delivery_output=delivery_result,
            visual_output=visual_result,
            synthesis_output=synthesis_result,
            synthesis_meta=synthesis_meta,
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


def _fallback_analysis_output(*, branch: str, detail: str) -> dict[str, object]:
    title = {'contenido': 'Contenido', 'delivery': 'Delivery', 'visual': 'Visual'}.get(branch, branch.title())
    details = [f'Fallo controlado en rama {branch}: {detail}']
    base: dict[str, object] = {
        'block_id': branch,
        'title': title,
        'status_visual': 'placeholder',
        'score_0_100': 40,
        'summary': f'Evaluación degradada de {branch} por error de ejecución en la rama paralela.',
        'details': details,
        'recommendations': ['Reintenta la evaluación para recuperar el diagnóstico completo de esta rama.'],
    }
    if branch == 'visual':
        base['evidence_frames'] = []
    return base


def _run_parallel_communication_analyses(
    *,
    evaluation_id: str,
    attempt_id: str,
    bundle: object,
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, str]]:
    branch_specs = {
        'contenido': ('content_analysis_started', 'content_analysis_ready', evaluate_communication_content),
        'delivery': ('delivery_analysis_started', 'delivery_analysis_ready', evaluate_communication_delivery),
        'visual': ('visual_analysis_started', 'visual_analysis_ready', evaluate_communication_visual),
    }
    futures: dict[Future[dict[str, object]], str] = {}
    errors: dict[str, str] = {}
    results: dict[str, dict[str, object]] = {}
    errors_lock = threading.Lock()

    def _run_branch(branch: str) -> dict[str, object]:
        started_stage, ready_stage, evaluator = branch_specs[branch]
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage=started_stage)
        try:
            result = evaluator(bundle)
        except Exception as exc:  # pragma: no cover - defensive branch
            detail = f'{type(exc).__name__}:{exc}'
            with errors_lock:
                errors[branch] = detail
            result = _fallback_analysis_output(branch=branch, detail=detail)
        _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage=ready_stage)
        return result

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix='communication_eval_branches') as executor:
        for branch in branch_specs:
            future = executor.submit(_run_branch, branch)
            futures[future] = branch
        try:
            for future in as_completed(futures, timeout=_PARALLEL_ANALYSIS_TIMEOUT_SECONDS):
                branch = futures[future]
                results[branch] = future.result()
        except TimeoutError:
            for future, branch in futures.items():
                if branch in results:
                    continue
                future.cancel()
                errors[branch] = f'timeout>{_PARALLEL_ANALYSIS_TIMEOUT_SECONDS}s'
                results[branch] = _fallback_analysis_output(branch=branch, detail=errors[branch])
                _, ready_stage, _ = branch_specs[branch]
                _set_job(evaluation_id=evaluation_id, attempt_id=attempt_id, status='running', stage=ready_stage)

    content = results.get('contenido') or _fallback_analysis_output(branch='contenido', detail='missing_result')
    delivery = results.get('delivery') or _fallback_analysis_output(branch='delivery', detail='missing_result')
    visual = results.get('visual') or _fallback_analysis_output(branch='visual', detail='missing_result')
    return content, delivery, visual, errors


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


def persist_audio_metrics_artifact(*, evaluation_id: str, bundle: object) -> None:
    audio_features = getattr(bundle, 'audio_features', None)
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if audio_features is None or attempt_ref is None:
        return
    if getattr(audio_features, 'status', None) != 'ready':
        return
    storage_ref = f'memory://communication/audio_metrics/{evaluation_id}/{getattr(attempt_ref, "recording_id", "unknown")}.json'
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='audio_metrics_real',
            version=getattr(audio_features, 'schema_version', 'communication_audio_features_real.v1'),
            storage_ref=storage_ref,
            content_hash=None,
            created_at=_utcnow(),
        )
    )


def persist_frame_manifest_artifact(*, evaluation_id: str, bundle: object) -> None:
    visual_features = getattr(bundle, 'visual_features', None)
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if visual_features is None or attempt_ref is None:
        return
    if getattr(visual_features, 'status', None) != 'ready':
        return
    storage_ref = f'memory://communication/frames/{evaluation_id}/{getattr(attempt_ref, "recording_id", "unknown")}.json'
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='frame_manifest',
            version=getattr(getattr(visual_features, 'frame_manifest', None), 'schema_version', 'communication_frame_manifest.v1'),
            storage_ref=storage_ref,
            content_hash=None,
            created_at=_utcnow(),
        )
    )


def persist_visual_evaluation_artifact(*, evaluation_id: str, bundle: object) -> None:
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if attempt_ref is None:
        return
    storage_ref = f'memory://communication/visual_evaluation/{evaluation_id}/{getattr(attempt_ref, "recording_id", "unknown")}.json'
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='visual_evaluation',
            version='communication_visual_evaluation.v1',
            storage_ref=storage_ref,
            content_hash=None,
            created_at=_utcnow(),
        )
    )


def persist_visual_batch_eval_artifacts(*, evaluation_id: str, bundle: object, visual_output: dict[str, object]) -> None:
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if attempt_ref is None:
        return
    raw_batches = visual_output.get('llm_batch_evaluations')
    if not isinstance(raw_batches, list):
        return
    for index, _payload in enumerate(raw_batches, start=1):
        storage_ref = (
            f'memory://communication/visual_batch_eval/{evaluation_id}/'
            f'{getattr(attempt_ref, "recording_id", "unknown")}/batch_{index}.json'
        )
        REPOSITORY.save_artifact(
            DerivedArtifactRecord(
                artifact_id=_generate_artifact_id(),
                recording_id=getattr(attempt_ref, 'recording_id'),
                kind='visual_batch_eval',
                version='communication_visual_batch_eval.v2',
                storage_ref=storage_ref,
                content_hash=None,
                created_at=_utcnow(),
            )
        )


def persist_visual_llm_final_artifact(*, evaluation_id: str, bundle: object, visual_output: dict[str, object]) -> None:
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if attempt_ref is None:
        return
    raw_final = visual_output.get('llm_final_evaluation')
    if not isinstance(raw_final, dict) or not raw_final:
        return
    storage_ref = (
        f'memory://communication/visual_llm_final/{evaluation_id}/'
        f'{getattr(attempt_ref, "recording_id", "unknown")}.json'
    )
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='visual_llm_final',
            version='communication_specialized_dimension_eval.v1',
            storage_ref=storage_ref,
            content_hash=None,
            created_at=_utcnow(),
        )
    )


def persist_global_synthesis_artifact(*, evaluation_id: str, bundle: object) -> None:
    attempt_ref = getattr(bundle, 'attempt_ref', None)
    if attempt_ref is None:
        return
    storage_ref = f'memory://communication/global_synthesis/{evaluation_id}/{getattr(attempt_ref, "recording_id", "unknown")}.json'
    REPOSITORY.save_artifact(
        DerivedArtifactRecord(
            artifact_id=_generate_artifact_id(),
            recording_id=getattr(attempt_ref, 'recording_id'),
            kind='global_synthesis',
            version='communication_global_synthesis_output.v1',
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
