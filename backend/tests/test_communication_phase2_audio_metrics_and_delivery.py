from __future__ import annotations

import math
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from comunicacion.storage import REPOSITORY
from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioFeaturesRealV1,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioPauseEvent,
    CommunicationAudioPitchStats,
    CommunicationAudioRawMetricsV1,
)
from evaluacion.engine.communication_audio_metrics import (
    build_audio_features_real,
    extract_pause_metrics,
)
from evaluacion.engine.communication_delivery_evaluator import (
    evaluate_delivery_from_audio_metrics,
    validate_delivery_eval_schema,
)
from evaluacion.engine.communication_service import persist_audio_metrics_artifact


def _write_test_wave(path: Path, *, sample_rate: int = 16000) -> None:
    one_second = sample_rate
    half_second = sample_rate // 2
    signal: list[float] = []

    def append_tone(*, hz: float, amplitude: float, sample_count: int) -> None:
        for idx in range(sample_count):
            t = idx / sample_rate
            signal.append(amplitude * math.sin(2.0 * math.pi * hz * t))

    append_tone(hz=190.0, amplitude=0.4, sample_count=one_second)
    signal.extend([0.0] * half_second)
    append_tone(hz=220.0, amplitude=0.35, sample_count=one_second)
    signal.extend([0.0] * half_second)
    append_tone(hz=180.0, amplitude=0.3, sample_count=one_second)

    pcm = array('h')
    for sample in signal:
        scaled = int(max(-32768, min(32767, round(sample * 32767))))
        pcm.append(scaled)

    with wave.open(str(path), 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


class CommunicationPhase2AudioMetricsAndDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def test_extract_pause_metrics_detects_pause_windows(self) -> None:
        rms = [0.2, 0.21, 0.01, 0.009, 0.008, 0.2, 0.2, 0.006, 0.005, 0.2]
        events, pause_time_ms, long_pauses = extract_pause_metrics(rms_values=rms, frame_ms=100, long_pause_ms=250)
        self.assertGreaterEqual(len(events), 2)
        self.assertGreater(pause_time_ms, 0)
        self.assertGreaterEqual(long_pauses, 1)

    def test_build_audio_features_real_uses_signal_and_not_only_duration(self) -> None:
        with tempfile.TemporaryDirectory(prefix='comm_phase2_') as tmpdir:
            wav_path = Path(tmpdir) / 'audio_metrics.wav'
            _write_test_wave(wav_path)
            raw, interpreted, quality_flags = build_audio_features_real(
                audio_path=wav_path,
                transcript_words=80,
                provider_meta={'source': 'unit_test'},
            )
        self.assertGreaterEqual(len(raw.pause_events), 1)
        self.assertIsNotNone(raw.speech_rate_wpm)
        self.assertGreater(raw.speaking_time_ms, 0)
        self.assertGreaterEqual(raw.pause_ratio, 0.0)
        self.assertIsNotNone(raw.pitch_stats.mean_hz)
        self.assertGreater(raw.energy_stats.rms_mean, 0.0)
        self.assertIn(interpreted.fluency_1_5, [1, 2, 3, 4, 5])
        self.assertIsInstance(quality_flags, list)

    def test_delivery_evaluation_has_stable_schema_and_evidence(self) -> None:
        audio_features = CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[CommunicationAudioPauseEvent(start_ms=1000, end_ms=1600, duration_ms=600)],
                speech_rate_wpm=132.4,
                speaking_time_ms=42000,
                pause_time_ms=6000,
                pause_ratio=0.125,
                pause_mean_ms=600.0,
                pause_max_ms=600,
                long_pauses_count=0,
                pitch_stats=CommunicationAudioPitchStats(mean_hz=210.0, median_hz=208.0, std_hz=26.0, min_hz=170.0, max_hz=255.0, range_hz=85.0),
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.18, rms_std=0.04, rms_min=0.03, rms_max=0.38),
                voiced_ratio=0.71,
            ),
            interpreted_metrics=CommunicationAudioInterpretedMetricsV1(
                fluency_1_5=4,
                pause_control_1_5=4,
                expressiveness_1_5=3,
                stability_1_5=4,
            ),
            quality_flags=[],
            provider_meta={'source': 'unit_test'},
            explanation='ok',
        )
        evaluated = evaluate_delivery_from_audio_metrics(audio_features=audio_features, transcript_excerpt='Texto breve.')
        validated = validate_delivery_eval_schema(evaluated.model_dump(mode='json'))
        self.assertGreaterEqual(validated.score_0_100, 0)
        self.assertTrue(validated.evidence_metrics)
        self.assertTrue(validated.observations)
        self.assertTrue(validated.recommendations)

    def test_persist_audio_metrics_artifact(self) -> None:
        audio_features = CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[],
                speech_rate_wpm=120.0,
                speaking_time_ms=10000,
                pause_time_ms=1000,
                pause_ratio=0.1,
                pause_mean_ms=None,
                pause_max_ms=None,
                long_pauses_count=0,
                pitch_stats=CommunicationAudioPitchStats(),
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.2, rms_std=0.03, rms_min=0.01, rms_max=0.34),
                voiced_ratio=0.75,
            ),
            interpreted_metrics=CommunicationAudioInterpretedMetricsV1(),
            quality_flags=[],
            provider_meta={},
            explanation='ok',
        )

        bundle = type('Bundle', (), {})()
        bundle.audio_features = audio_features
        bundle.attempt_ref = type('AttemptRef', (), {'recording_id': 'rec_audio_metrics'})()

        persist_audio_metrics_artifact(evaluation_id='eval_audio_metrics', bundle=bundle)
        artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_audio_metrics', 'audio_metrics_real')
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0].kind, 'audio_metrics_real')
