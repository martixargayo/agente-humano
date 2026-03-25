from __future__ import annotations

from fastapi import HTTPException

from comunicacion.storage import REPOSITORY
from evaluacion.contracts.communication_models import (
    CommunicationAttemptRef,
    CommunicationFeedbackInputBundleV1,
    CommunicationRecordingMetadata,
)
from evaluacion.contracts.models import SessionRef
from evaluacion.domains.communication import (
    build_real_audio_features,
    build_placeholder_audio_features,
    build_placeholder_transcript,
    build_real_transcript,
    build_placeholder_visual_features,
    resolve_communication_evaluation_context_from_attempt,
)
from evaluacion.engine.communication_stt import CommunicationSttProvider


def build_communication_feedback_input_bundle(
    *, evaluation_id: str, attempt_id: str, stt_provider: CommunicationSttProvider | None = None
) -> CommunicationFeedbackInputBundleV1:
    attempt = REPOSITORY.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(status_code=404, detail={'error': 'attempt_not_found', 'attempt_id': attempt_id})
    if not attempt.recording_id:
        raise HTTPException(
            status_code=409,
            detail={'error': 'attempt_recording_required', 'attempt_id': attempt_id},
        )

    recording = REPOSITORY.get_recording(attempt.recording_id)
    if recording is None:
        raise HTTPException(
            status_code=404,
            detail={'error': 'recording_not_found', 'recording_id': attempt.recording_id},
        )

    domain_context = resolve_communication_evaluation_context_from_attempt(attempt=attempt)
    recording_meta = CommunicationRecordingMetadata(
        duration_ms=recording.duration_ms,
        mime_type=recording.mime_type,
        video_ref=recording.video_ref,
        poster_frame_ref=recording.poster_frame_ref,
        capture_meta=recording.capture_meta,
    )

    try:
        transcript = build_real_transcript(recording=recording, provider=stt_provider)
    except HTTPException:
        transcript = build_placeholder_transcript(recording=recording)
    transcript_words = len([token for token in (transcript.full_text or '').split() if token])
    try:
        audio_features = build_real_audio_features(recording=recording, transcript_words=transcript_words)
    except HTTPException:
        audio_features = build_placeholder_audio_features(recording=recording)

    return CommunicationFeedbackInputBundleV1(
        evaluation_id=evaluation_id,
        session_ref=SessionRef(user_id=attempt.user_id, session_id=attempt.session_id),
        attempt_ref=CommunicationAttemptRef(attempt_id=attempt.attempt_id, recording_id=recording.recording_id),
        domain_context=domain_context,
        recording=recording_meta,
        transcript=transcript,
        audio_features=audio_features,
        visual_features=build_placeholder_visual_features(recording=recording),
    )
