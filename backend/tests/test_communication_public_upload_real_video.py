from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.app import app
from comunicacion.storage import REPOSITORY
from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioFeaturesRealV1,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioPitchStats,
    CommunicationAudioRawMetricsV1,
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationFrameWindow,
    CommunicationTranscriptRealV1,
    CommunicationTranscriptSegment,
    CommunicationVisualFeaturesRealV1,
)
from evaluacion.engine.communication_bundle_builder import build_communication_feedback_input_bundle
from evaluacion.engine.communication_media_processing import CommunicationAudioTrackArtifact, resolve_recording_media_source
from sessions.state import SESSIONS


class CommunicationPublicUploadRealVideoTests(unittest.TestCase):
    def setUp(self) -> None:
        SESSIONS.clear()
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()
        self.client = TestClient(app, raise_server_exceptions=False)
        self.client.post('/api/comunicacion/sessions/bootstrap', json={'user_id': 'iu_public_real', 'session_id': 'sess_public_real'})

    def _upload_dummy_binary(self, attempt_id: str) -> dict:
        payload = self.client.post(
            f"/api/comunicacion/attempts/{attempt_id}/upload",
            data={
                'user_id': 'iu_public_real',
                'session_id': 'sess_public_real',
                'mime_type': 'video/webm',
                'duration_ms': '2000',
                'capture_meta': '{"uploaded_from":"test"}',
            },
            files={'video_file': ('fixture.webm', b'RIFF....WEBM...binary', 'video/webm')},
        )
        self.assertEqual(payload.status_code, 200)
        return payload.json()

    def test_multipart_upload_persists_file_ref_resolvable_by_backend(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_public_real', 'session_id': 'sess_public_real'}).json()
        upload = self._upload_dummy_binary(attempt['attempt_id'])

        self.assertTrue(upload['video_ref'].startswith('file://'))
        stored_path = Path(upload['video_ref'].replace('file://', ''))
        self.assertTrue(stored_path.exists())

        recording = REPOSITORY.get_recording(upload['recording_id'])
        self.assertIsNotNone(recording)
        source = resolve_recording_media_source(recording=recording)
        self.assertEqual(source.local_path, stored_path)

    def test_pipeline_nominal_path_after_real_upload_uses_real_bundle_builders(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_public_real', 'session_id': 'sess_public_real'}).json()
        upload = self._upload_dummy_binary(attempt['attempt_id'])

        recording = REPOSITORY.get_recording(upload['recording_id'])
        self.assertIsNotNone(recording)
        fake_audio_file = Path(tempfile.gettempdir()) / 'comm_fake_audio.wav'
        fake_audio_file.write_bytes(b'RIFFFAKEAUDIO')
        audio_track = CommunicationAudioTrackArtifact(
            source_ref=f'file://{fake_audio_file}',
            audio_path=fake_audio_file,
            mime_type='audio/wav',
            is_temporary=False,
        )
        transcript = CommunicationTranscriptRealV1(
            provider='mock_word_timed_stt',
            language='es',
            full_text='Texto transcrito real para flujo nominal.',
            segments=[CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1100, text='Texto transcrito real para flujo nominal.')],
            confidence_global=0.95,
            quality_flags=[],
            explanation='mock transcript',
        )
        audio_features = CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[],
                speech_rate_wpm=130.0,
                speaking_time_ms=1500,
                pause_time_ms=200,
                pause_ratio=0.11,
                pause_mean_ms=200.0,
                pause_max_ms=200,
                long_pauses_count=0,
                pitch_stats=CommunicationAudioPitchStats(mean_hz=200.0, median_hz=198.0, std_hz=30.0, min_hz=150.0, max_hz=240.0, range_hz=90.0),
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.2, rms_std=0.03, rms_min=0.02, rms_max=0.32),
                voiced_ratio=0.73,
            ),
            interpreted_metrics=CommunicationAudioInterpretedMetricsV1(fluency_1_5=4, pause_control_1_5=4, expressiveness_1_5=4, stability_1_5=4),
            quality_flags=[],
            provider_meta={},
            explanation='real audio features',
        )
        frame_manifest = CommunicationFrameManifestV1(
            source_ref=upload['video_ref'],
            sampling_policy={'sample_every_ms': 1500, 'max_frames': 12, 'window_size': 4},
            frames=[CommunicationFrameSample(frame_id='frame_001', timestamp_ms=0, frame_ref='file:///tmp/frame_001.jpg', quality='ok')],
            windows=[CommunicationFrameWindow(window_id='window_1', start_ms=0, end_ms=0, frame_ids=['frame_001'])],
        )
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=frame_manifest,
            coverage_stats={'expected_frames': 1, 'extracted_frames': 1, 'coverage_ratio': 1.0},
            quality_flags=[],
            explanation='real visual features',
        )

        with patch('evaluacion.engine.communication_bundle_builder.prepare_media_artifacts', return_value=(object(), audio_track, frame_manifest)), patch(
            'evaluacion.engine.communication_bundle_builder.build_real_transcript_from_audio_track', return_value=transcript
        ), patch('evaluacion.engine.communication_bundle_builder.build_real_audio_features_from_audio_track', return_value=audio_features), patch(
            'evaluacion.engine.communication_bundle_builder.build_real_visual_features_from_manifest', return_value=visual_features
        ):
            bundle = build_communication_feedback_input_bundle(evaluation_id='eval_nominal', attempt_id=attempt['attempt_id'])

        self.assertEqual(bundle.transcript.status, 'ready')
        self.assertEqual(bundle.audio_features.status, 'ready')
        self.assertEqual(bundle.visual_features.status, 'ready')

    def test_fallback_degradation_remains_when_upload_persists_only_client_temp_metadata(self) -> None:
        attempt = self.client.post('/api/comunicacion/attempts', json={'user_id': 'iu_public_real', 'session_id': 'sess_public_real'}).json()
        self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/upload",
            json={
                'user_id': 'iu_public_real',
                'session_id': 'sess_public_real',
                'mime_type': 'video/webm',
                'duration_ms': 12000,
                'video_ref': 'client-temp://sess_public_real/att_diag/1710000000000.webm',
                'capture_meta': {'provisional_client_ref': True},
            },
        )
        submit = self.client.post(
            f"/api/comunicacion/attempts/{attempt['attempt_id']}/submit",
            json={'user_id': 'iu_public_real', 'session_id': 'sess_public_real'},
        ).json()
        evaluation_id = submit['evaluation_id']
        for _ in range(40):
            status = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}').json()
            if status['status'] == 'completed':
                break
            time.sleep(0.05)

        report = self.client.get(f'/api/comunicacion/evaluations/{evaluation_id}/report').json()
        delivery = next(block for block in report['block_cards'] if block['block_id'] == 'delivery')
        visual = next(block for block in report['block_cards'] if block['block_id'] == 'visual')
        self.assertIn('No hay métricas acústicas reales disponibles todavía en esta ejecución.', delivery['details'])
        self.assertIn('No hay frame manifest real disponible; evaluación visual degradada a modo placeholder.', visual['details'])


if __name__ == '__main__':
    unittest.main()
