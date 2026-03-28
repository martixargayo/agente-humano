from __future__ import annotations

import unittest
from datetime import datetime, timezone
from os import environ
from unittest.mock import patch

from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioFeaturesRealV1,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioPitchStats,
    CommunicationAudioRawMetricsV1,
    CommunicationContentAidaEvalV1,
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationFrameWindow,
    CommunicationGlobalSynthesisLlmOutputV1,
    CommunicationSpecializedDimensionEvalV1,
    CommunicationTranscriptRealV1,
    CommunicationTranscriptSegment,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualEvaluationV1,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualFrameCoverageSummaryV1,
    CommunicationVisualObservabilityFlagsV1,
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

    def test_pipeline_e2e_with_all_llm_paths_enabled(self) -> None:
        evaluation_id, attempt_id = self._seed()

        transcript = CommunicationTranscriptRealV1(
            provider='mock_stt',
            language='es',
            full_text='Inicio con gancho. Desarrollo con claridad. Cierre con llamada a la acción.',
            segments=[
                CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1500, text='Inicio con gancho.'),
                CommunicationTranscriptSegment(segment_index=2, start_ms=1500, end_ms=4500, text='Desarrollo con claridad.'),
                CommunicationTranscriptSegment(segment_index=3, start_ms=4500, end_ms=7000, text='Cierre con llamada a la acción.'),
            ],
            confidence_global=0.96,
            quality_flags=[],
            explanation='ok',
        )
        audio_features = CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[],
                speech_rate_wpm=125.0,
                speaking_time_ms=8900,
                pause_time_ms=1300,
                pause_ratio=0.13,
                pause_mean_ms=280.0,
                pause_max_ms=620,
                long_pauses_count=0,
                pitch_stats=CommunicationAudioPitchStats(mean_hz=205.0, median_hz=203.0, std_hz=28.0, min_hz=160.0, max_hz=248.0, range_hz=88.0),
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.19, rms_std=0.04, rms_min=0.03, rms_max=0.39),
                voiced_ratio=0.74,
            ),
            interpreted_metrics=CommunicationAudioInterpretedMetricsV1(fluency_1_5=4, pause_control_1_5=4, expressiveness_1_5=4, stability_1_5=4),
            quality_flags=[],
            provider_meta={},
            explanation='ok',
        )
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=CommunicationFrameManifestV1(
                source_ref='file:///tmp/nonexistent_audit_llm.webm',
                sampling_policy={'sample_every_ms': 1000, 'max_frames': 10, 'window_size': 4},
                frames=[
                    CommunicationFrameSample(frame_id='frame_001', timestamp_ms=0, frame_ref='file:///tmp/f1.jpg', quality='ok'),
                    CommunicationFrameSample(frame_id='frame_002', timestamp_ms=1000, frame_ref='file:///tmp/f2.jpg', quality='ok'),
                    CommunicationFrameSample(frame_id='frame_003', timestamp_ms=2000, frame_ref='file:///tmp/f3.jpg', quality='ok'),
                ],
                windows=[CommunicationFrameWindow(window_id='window_1', start_ms=0, end_ms=2000, frame_ids=['frame_001', 'frame_002', 'frame_003'])],
            ),
            coverage_stats={'expected_frames': 10, 'extracted_frames': 3, 'coverage_ratio': 0.3},
            quality_flags=[],
            explanation='ok',
        )

        aida_eval = CommunicationContentAidaEvalV1(
            attention={'score_1_3': 3, 'label': 'correcto', 'reason_short': 'Arrancas con gancho y foco.'},
            interest={'score_1_3': 3, 'label': 'correcto', 'reason_short': 'Conectas bien con el valor para la audiencia.'},
            development={'score_1_3': 3, 'label': 'correcto', 'reason_short': 'Desarrollas con orden y claridad.'},
            action={'score_1_3': 2, 'label': 'mejorable', 'reason_short': 'Tu cierre orienta, pero puede ser más contundente.'},
        )
        audio_specialized = CommunicationSpecializedDimensionEvalV1(
            score_1_5=4,
            label='medio-alto',
            reason_short='Tus pausas sostienen bien la claridad y tu variación vocal acompaña de forma útil.',
        )
        batch_eval = CommunicationVisualBatchEvalV2(
            batch_index=1,
            total_batches=1,
            batch_score_1_5=4,
            evidence_sufficiency='medium',
            confidence=0.7,
            hand_use_assessment='Uso funcional y visible en varios frames.',
            facial_expression_assessment='Expresividad suficiente y estable.',
            posture_assessment='Postura abierta en la mayor parte del lote.',
            visual_support_assessment='La presencia visual acompaña el mensaje.',
            strengths=['Buena presencia corporal general.'],
            weaknesses=['Puede variar más en momentos clave.'],
            limitations=[],
            cited_frame_ids=['frame_001'],
            observability_flags=CommunicationVisualObservabilityFlagsV1(
                hands_not_visible=False,
                face_partially_visible=False,
                upper_body_not_visible=False,
                blur_detected=False,
                low_light_detected=False,
                camera_far_distance=False,
            ),
            frame_coverage_summary=CommunicationVisualFrameCoverageSummaryV1(
                frames_total=3,
                frames_usable=3,
                frames_with_face_visible=3,
                frames_with_hands_visible=2,
                frames_with_upper_body_visible=3,
                frames_blurry=0,
                frames_low_light=0,
            ),
            confidence_reasoning=['Cobertura suficiente para estimación estable.'],
        )
        visual_eval = CommunicationVisualEvaluationV1(
            score_0_100=80,
            subscores={'gesticulation_global': 4},
            temporal_findings=[],
            observations=['Se observa apoyo visual consistente.'],
            recommendations=['Sostén la apertura corporal al cerrar.'],
            evidence_frames=['frame_001'],
        )
        visual_final = CommunicationSpecializedDimensionEvalV1(
            score_1_5=4,
            label='medio-alto',
            reason_short='Tu apoyo gestual acompaña bien el mensaje y puede ganar más intención al cerrar.',
        )
        final_synthesis = CommunicationGlobalSynthesisLlmOutputV1(
            score_global_100=84,
            summary_short_2_3_lines='Has construido una comunicación sólida y clara, con fortalezas visibles en estructura y control, aunque todavía puedes reforzar el cierre para dejar más huella.',
            recommendations=[
                {
                    'title': 'Haz el cierre más intencional',
                    'description': 'Termina con una idea final más concreta para reforzar el mensaje principal.',
                }
            ],
        )

        with patch.dict(
            environ,
            {
                'COMMUNICATION_FORCE_SAFE_MODE': 'false',
            },
        ), patch('evaluacion.engine.communication_bundle_builder.build_real_transcript', return_value=transcript), patch(
            'evaluacion.engine.communication_bundle_builder.build_real_audio_features', return_value=audio_features
        ), patch('evaluacion.engine.communication_bundle_builder.build_real_visual_features', return_value=visual_features), patch(
            'evaluacion.engine.communication_content_evaluator._run_content_llm_openai',
            return_value=aida_eval,
        ), patch(
            'evaluacion.engine.communication_delivery_evaluator._run_audio_specialized_eval_openai',
            return_value=audio_specialized,
        ), patch(
            'evaluacion.engine.communication_evaluators.evaluate_visual_llm_v1_from_features',
            return_value=(visual_eval, [batch_eval], visual_final),
        ), patch(
            'evaluacion.engine.communication_synthesis._run_global_synthesis_llm_openai',
            return_value=final_synthesis,
        ):
            run_communication_evaluation_job_inline_for_tests(evaluation_id=evaluation_id, attempt_id=attempt_id)

        report = REPOSITORY._communication_eval_reports[evaluation_id]
        self.assertEqual(report.status, 'completed')
        self.assertIsNotNone(report.global_synthesis)
        self.assertEqual(report.global_synthesis.score_global_100, 84)
        self.assertEqual(
            report.global_synthesis.summary_short_2_3_lines,
            final_synthesis.summary_short_2_3_lines,
        )
        self.assertEqual(len(report.global_synthesis.recommendations), 1)
        self.assertNotIn('\n\n', report.global_synthesis.summary_short_2_3_lines)

        kinds = {artifact.kind for artifact in REPOSITORY.list_artifacts_for_recording('rec_audit_e2e')}
        self.assertTrue({'visual_batch_eval', 'visual_llm_final', 'global_synthesis'}.issubset(kinds))


if __name__ == '__main__':
    unittest.main()
