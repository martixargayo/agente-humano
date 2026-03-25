from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from comunicacion.storage.models import RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationAudioFeaturesRealV1,
    CommunicationAudioFeaturesPlaceholder,
    CommunicationFrameManifestV1,
    CommunicationPauseSegment,
    CommunicationTranscriptPlaceholder,
    CommunicationTranscriptSegment,
    CommunicationTranscriptRealV1,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualFeaturesPlaceholder,
)
from evaluacion.engine.communication_frame_extractor import extract_video_frames
from evaluacion.engine.communication_audio_metrics import build_audio_features_real
from evaluacion.engine.communication_media_processing import (
    CommunicationAudioTrackArtifact,
    extract_audio_track,
    resolve_recording_media_source,
)
from evaluacion.engine.communication_stt import CommunicationSttProvider, transcribe_audio


@dataclass(frozen=True)
class CommunicationPreparedMediaArtifacts:
    media_source_ref: str
    audio_track_ref: str | None
    frame_count: int


def prepare_media_artifacts(*, recording: RecordingRecord) -> tuple[CommunicationPreparedMediaArtifacts, CommunicationAudioTrackArtifact, CommunicationFrameManifestV1]:
    media_source = resolve_recording_media_source(recording=recording)
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='communication_media_prepare') as executor:
        audio_future = executor.submit(extract_audio_track, media_source=media_source, recording=recording)
        frames_future = executor.submit(
            extract_video_frames,
            media_source=media_source,
            recording=recording,
            sample_every_ms=1500,
            max_frames=12,
            window_size=4,
        )
        audio_track = audio_future.result()
        frame_manifest = frames_future.result()
    prepared = CommunicationPreparedMediaArtifacts(
        media_source_ref=media_source.source_ref,
        audio_track_ref=str(audio_track.source_ref),
        frame_count=len(frame_manifest.frames),
    )
    return prepared, audio_track, frame_manifest


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


def build_real_transcript(*, recording: RecordingRecord, provider: CommunicationSttProvider | None = None) -> CommunicationTranscriptRealV1:
    media_source = resolve_recording_media_source(recording=recording)
    audio_track = extract_audio_track(media_source=media_source, recording=recording)
    transcript_artifact = transcribe_audio(audio_path=audio_track.audio_path, language_hint='es', provider=provider)
    return transcript_artifact.transcript


def build_real_transcript_from_audio_track(*, audio_track: CommunicationAudioTrackArtifact, provider: CommunicationSttProvider | None = None) -> CommunicationTranscriptRealV1:
    transcript_artifact = transcribe_audio(audio_path=audio_track.audio_path, language_hint='es', provider=provider)
    return transcript_artifact.transcript


def build_real_audio_features(*, recording: RecordingRecord, transcript_words: int) -> CommunicationAudioFeaturesRealV1:
    media_source = resolve_recording_media_source(recording=recording)
    audio_track = extract_audio_track(media_source=media_source, recording=recording)
    raw_metrics, interpreted_metrics, quality_flags = build_audio_features_real(
        audio_path=audio_track.audio_path,
        transcript_words=transcript_words,
        provider_meta={'extractor': 'communication_audio_metrics', 'audio_ref': str(audio_track.source_ref)},
    )
    status = 'ready'
    explanation = 'Métricas acústicas reales calculadas desde señal de audio.'
    if not raw_metrics.speaking_time_ms:
        status = 'unavailable'
        quality_flags = list(quality_flags) + ['speaking_time_unavailable']
        explanation = 'No se pudo calcular speaking_time utilizable; se degrada evaluación de delivery.'
    return CommunicationAudioFeaturesRealV1(
        status=status,
        raw_metrics=raw_metrics,
        interpreted_metrics=interpreted_metrics,
        quality_flags=quality_flags,
        provider_meta={'audio_path': str(audio_track.audio_path), 'mime_type': audio_track.mime_type},
        explanation=explanation,
    )


def build_real_audio_features_from_audio_track(*, audio_track: CommunicationAudioTrackArtifact, transcript_words: int) -> CommunicationAudioFeaturesRealV1:
    raw_metrics, interpreted_metrics, quality_flags = build_audio_features_real(
        audio_path=audio_track.audio_path,
        transcript_words=transcript_words,
        provider_meta={'extractor': 'communication_audio_metrics', 'audio_ref': str(audio_track.source_ref)},
    )
    status = 'ready'
    explanation = 'Métricas acústicas reales calculadas desde señal de audio.'
    if not raw_metrics.speaking_time_ms:
        status = 'unavailable'
        quality_flags = list(quality_flags) + ['speaking_time_unavailable']
        explanation = 'No se pudo calcular speaking_time utilizable; se degrada evaluación de delivery.'
    return CommunicationAudioFeaturesRealV1(
        status=status,
        raw_metrics=raw_metrics,
        interpreted_metrics=interpreted_metrics,
        quality_flags=quality_flags,
        provider_meta={'audio_path': str(audio_track.audio_path), 'mime_type': audio_track.mime_type},
        explanation=explanation,
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


def build_real_visual_features(*, recording: RecordingRecord) -> CommunicationVisualFeaturesRealV1:
    media_source = resolve_recording_media_source(recording=recording)
    manifest = extract_video_frames(
        media_source=media_source,
        recording=recording,
        sample_every_ms=1500,
        max_frames=12,
        window_size=4,
    )
    expected_frames = max(1, min(12, int((recording.duration_ms / 1500) + 0.999)))
    coverage_ratio = min(len(manifest.frames) / expected_frames, 1.0)
    quality_flags: list[str] = []
    if any(frame.quality == 'low_detail' for frame in manifest.frames):
        quality_flags.append('low_detail_frames_detected')
    status = 'ready'
    explanation = 'Frame manifest real extraído desde video para evaluación visual estructurada.'
    if not manifest.frames:
        status = 'unavailable'
        quality_flags.append('no_frames_extracted')
        explanation = 'No fue posible extraer frames utilizables del video.'
    return CommunicationVisualFeaturesRealV1(
        status=status,
        frame_manifest=manifest if manifest.frames else CommunicationFrameManifestV1(source_ref=recording.video_ref),
        coverage_stats={
            'expected_frames': expected_frames,
            'extracted_frames': len(manifest.frames),
            'coverage_ratio': round(coverage_ratio, 4),
        },
        quality_flags=quality_flags,
        explanation=explanation,
    )


def build_real_visual_features_from_manifest(*, recording: RecordingRecord, manifest: CommunicationFrameManifestV1) -> CommunicationVisualFeaturesRealV1:
    expected_frames = max(1, min(12, int((recording.duration_ms / 1500) + 0.999)))
    coverage_ratio = min(len(manifest.frames) / expected_frames, 1.0)
    quality_flags: list[str] = []
    if any(frame.quality == 'low_detail' for frame in manifest.frames):
        quality_flags.append('low_detail_frames_detected')
    status = 'ready'
    explanation = 'Frame manifest real extraído desde video para evaluación visual estructurada.'
    if not manifest.frames:
        status = 'unavailable'
        quality_flags.append('no_frames_extracted')
        explanation = 'No fue posible extraer frames utilizables del video.'
    return CommunicationVisualFeaturesRealV1(
        status=status,
        frame_manifest=manifest if manifest.frames else CommunicationFrameManifestV1(source_ref=recording.video_ref),
        coverage_stats={
            'expected_frames': expected_frames,
            'extracted_frames': len(manifest.frames),
            'coverage_ratio': round(coverage_ratio, 4),
        },
        quality_flags=quality_flags,
        explanation=explanation,
    )
