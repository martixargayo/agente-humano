from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
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
from evaluacion.engine.communication_service import run_communication_evaluation_job_inline_for_tests


class CommunicationAuditPipelineE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def _seed(self) -> tuple[str, str]:
        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id='att_audit_e2e',
            user_id='iu_audit_e2e',
            session_id='sess_audit_e2e',
            context_id='baseline_current',
            status='uploaded',
            recording_id='rec_audit_e2e',
            created_at=now,
            updated_at=now,
        )
        recording = RecordingRecord(
            recording_id='rec_audit_e2e',
            attempt_id='att_audit_e2e',
            user_id='iu_audit_e2e',
            session_id='sess_audit_e2e',
            mime_type='video/webm',
            duration_ms=12000,
            video_ref='file:///tmp/nonexistent_audit.webm',
            created_at=now,
        )
        REPOSITORY.create_attempt(attempt)
        REPOSITORY.attach_recording(recording)
        return 'eval_audit_e2e', 'att_audit_e2e'

    def test_pipeline_persists_all_multimodal_artifacts_and_global_report(self) -> None:
        evaluation_id, attempt_id = self._seed()

        transcript = CommunicationTranscriptRealV1(
            provider='mock_stt',
            language='es',
            full_text='Inicio claro. Desarrollo sólido. Cierre correcto.',
            segments=[
                CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1500, text='Inicio claro.'),
                CommunicationTranscriptSegment(segment_index=2, start_ms=1500, end_ms=4500, text='Desarrollo sólido.'),
                CommunicationTranscriptSegment(segment_index=3, start_ms=4500, end_ms=7000, text='Cierre correcto.'),
            ],
            confidence_global=0.95,
            quality_flags=[],
            explanation='ok',
        )
        audio_features = CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[],
                speech_rate_wpm=130.0,
                speaking_time_ms=9000,
                pause_time_ms=1200,
                pause_ratio=0.12,
                pause_mean_ms=300.0,
                pause_max_ms=700,
                long_pauses_count=0,
                pitch_stats=CommunicationAudioPitchStats(mean_hz=200.0, median_hz=198.0, std_hz=30.0, min_hz=160.0, max_hz=245.0, range_hz=85.0),
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.2, rms_std=0.04, rms_min=0.03, rms_max=0.4),
                voiced_ratio=0.72,
            ),
            interpreted_metrics=CommunicationAudioInterpretedMetricsV1(fluency_1_5=4, pause_control_1_5=4, expressiveness_1_5=4, stability_1_5=4),
            quality_flags=[],
            provider_meta={},
            explanation='ok',
        )
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=CommunicationFrameManifestV1(
                source_ref='file:///tmp/nonexistent_audit.webm',
                sampling_policy={'sample_every_ms': 1500, 'max_frames': 12, 'window_size': 4},
                frames=[
                    CommunicationFrameSample(frame_id='frame_001', timestamp_ms=0, frame_ref='file:///tmp/f1.jpg', quality='ok'),
                    CommunicationFrameSample(frame_id='frame_002', timestamp_ms=1500, frame_ref='file:///tmp/f2.jpg', quality='ok'),
                ],
                windows=[CommunicationFrameWindow(window_id='window_1', start_ms=0, end_ms=1500, frame_ids=['frame_001', 'frame_002'])],
            ),
            coverage_stats={'expected_frames': 8, 'extracted_frames': 2, 'coverage_ratio': 0.25},
            quality_flags=[],
            explanation='ok',
        )

        with patch('evaluacion.engine.communication_bundle_builder.build_real_transcript', return_value=transcript), patch(
            'evaluacion.engine.communication_bundle_builder.build_real_audio_features', return_value=audio_features
        ), patch('evaluacion.engine.communication_bundle_builder.build_real_visual_features', return_value=visual_features):
            run_communication_evaluation_job_inline_for_tests(evaluation_id=evaluation_id, attempt_id=attempt_id)

        artifacts = REPOSITORY.list_artifacts_for_recording('rec_audit_e2e')
        kinds = {artifact.kind for artifact in artifacts}
        self.assertTrue({'transcript_real', 'audio_metrics_real', 'frame_manifest', 'visual_evaluation', 'global_synthesis'}.issubset(kinds))

        report = REPOSITORY._communication_eval_reports[evaluation_id]
        self.assertEqual(report.status, 'completed')
        self.assertIsNotNone(report.global_synthesis)
        self.assertTrue(report.exports.summary_html.startswith('<!doctype html>'))
        self.assertIn('global_synthesis', report.exports.report_json)


if __name__ == '__main__':
    unittest.main()
