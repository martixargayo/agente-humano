from __future__ import annotations

from comunicacion.storage.models import RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationAudioFeaturesPlaceholder,
    CommunicationPauseSegment,
    CommunicationTranscriptPlaceholder,
    CommunicationTranscriptSegment,
    CommunicationVisualFeaturesPlaceholder,
)


def build_placeholder_transcript(*, recording: RecordingRecord) -> CommunicationTranscriptPlaceholder:
    duration_ms = max(int(recording.duration_ms or 0), 1)
    intro = f'Registro {recording.recording_id} listo para evaluación mínima.'
    media_note = 'No existe transcripción automática real en esta fase; se expone un placeholder honesto derivado de metadata.'
    segment = CommunicationTranscriptSegment(
        segment_index=1,
        start_ms=0,
        end_ms=min(duration_ms, 5000),
        text=intro,
    )
    return CommunicationTranscriptPlaceholder(
        status='placeholder',
        language='es',
        full_text='',
        explanation=media_note,
        segments=[segment],
    )


def build_placeholder_audio_features(*, recording: RecordingRecord) -> CommunicationAudioFeaturesPlaceholder:
    duration_ms = max(int(recording.duration_ms or 0), 1)
    synthetic_pause = CommunicationPauseSegment(
        start_ms=max(duration_ms - 600, 0),
        end_ms=duration_ms,
        duration_ms=min(600, duration_ms),
        kind='synthetic_pause',
    )
    speech_rate = round(max(60.0, min(170.0, (duration_ms / 1000.0) * 1.15)), 1)
    return CommunicationAudioFeaturesPlaceholder(
        status='placeholder',
        speech_rate_wpm=speech_rate,
        filler_count=None,
        pause_segments=[synthetic_pause],
        explanation='No hay extracción acústica real todavía; las métricas son placeholders sintéticos para estabilizar contratos y stages.',
        metrics={
            'duration_ms': duration_ms,
            'synthetic_source': 'recording_metadata_only',
        },
    )


def build_placeholder_visual_features(*, recording: RecordingRecord) -> CommunicationVisualFeaturesPlaceholder:
    return CommunicationVisualFeaturesPlaceholder(
        status='placeholder',
        score_visual_0_100=None,
        summary='La analítica visual avanzada no forma parte del MVP actual.',
        explanation='Se conserva un bloque visual explícito para que el pipeline y el report no finjan capacidades inexistentes.',
        notable_windows=[],
    )
