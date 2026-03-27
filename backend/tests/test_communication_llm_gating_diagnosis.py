from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evaluacion.contracts.communication_models import (
    CommunicationAudioEnergyStats,
    CommunicationAudioFeaturesRealV1,
    CommunicationAudioInterpretedMetricsV1,
    CommunicationAudioRawMetricsV1,
    CommunicationContentAidaBlockEvalV1,
    CommunicationContentAidaEvalV1,
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationGlobalSynthesisLlmOutputV1,
    CommunicationSpecializedDimensionEvalV1,
    CommunicationTranscriptRealV1,
    CommunicationTranscriptSegment,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualEvaluationV1,
    CommunicationVisualObservabilityFlagsV1,
    CommunicationVisualFrameCoverageSummaryV1,
)
from evaluacion.engine.communication_content_evaluator import evaluate_content_from_transcript
from evaluacion.engine.communication_delivery_evaluator import evaluate_delivery_with_specialized_from_audio_metrics
from evaluacion.engine.communication_evaluators import (
    evaluate_communication_content,
    evaluate_communication_delivery,
    evaluate_communication_synthesis,
    evaluate_communication_visual,
)
from evaluacion.engine.communication_synthesis import build_global_synthesis_input, synthesize_global_communication_feedback


class CommunicationLlmGatingDiagnosisTests(unittest.TestCase):
    def _bundle_for_content(self):
        transcript = CommunicationTranscriptRealV1(
            provider='mock_stt',
            language='es',
            full_text='Hoy te cuento una idea con desarrollo claro y cierre accionable para practicar.',
            segments=[
                CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1500, text='Hoy te cuento una idea.'),
                CommunicationTranscriptSegment(segment_index=2, start_ms=1500, end_ms=3000, text='Con desarrollo claro y cierre accionable.'),
            ],
            confidence_global=0.9,
            quality_flags=[],
            explanation='ok',
        )
        bundle = type('Bundle', (), {})()
        bundle.evaluation_id = 'eval_diag_content'
        bundle.transcript = transcript
        return bundle

    def _audio_features_ready(self) -> CommunicationAudioFeaturesRealV1:
        return CommunicationAudioFeaturesRealV1(
            status='ready',
            raw_metrics=CommunicationAudioRawMetricsV1(
                pause_events=[],
                speech_rate_wpm=130.0,
                speaking_time_ms=20000,
                pause_time_ms=3000,
                pause_ratio=0.13,
                pause_mean_ms=450.0,
                pause_max_ms=700,
                long_pauses_count=0,
                pitch_stats={},
                energy_stats=CommunicationAudioEnergyStats(rms_mean=0.2, rms_std=0.03, rms_min=0.01, rms_max=0.35),
                voiced_ratio=0.8,
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

    def _bundle_for_visual(self):
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=CommunicationFrameManifestV1(
                source_ref='file:///tmp/video.mp4',
                sampling_policy={'sample_every_ms': 1000},
                frames=[
                    CommunicationFrameSample(
                        frame_id='frame_001',
                        timestamp_ms=0,
                        frame_ref='file:///tmp/frame_001.jpg',
                        quality='ok',
                    )
                ],
                windows=[],
            ),
            coverage_stats={'expected_frames': 1, 'extracted_frames': 1, 'coverage_ratio': 1.0},
            quality_flags=[],
            explanation='ok',
        )
        bundle = type('Bundle', (), {})()
        bundle.evaluation_id = 'eval_diag_visual'
        bundle.attempt_ref = type('AttemptRef', (), {'recording_id': 'rec_diag_visual'})()
        bundle.recording = type('RecordingMeta', (), {'duration_ms': 1000})()
        bundle.visual_features = visual_features
        return bundle

    def test_content_flag_off_sets_disabled_flag(self) -> None:
        with patch.dict(os.environ, {'COMM_CONTENT_OPENAI_ENABLED': 'false'}, clear=False):
            output = evaluate_content_from_transcript(bundle=self._bundle_for_content())
        self.assertEqual(output['runtime_meta']['mode'], 'fallback')
        self.assertEqual(output['runtime_meta']['reason'], 'disabled_flag')

    def test_content_flag_on_without_api_key_falls_back_missing_openai_api_key(self) -> None:
        with patch.dict(os.environ, {'COMM_CONTENT_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': ''}, clear=False):
            output = evaluate_content_from_transcript(bundle=self._bundle_for_content())
        self.assertEqual(output['runtime_meta']['mode'], 'fallback')
        self.assertEqual(output['runtime_meta']['reason'], 'missing_openai_api_key')

    def test_content_flag_on_with_mocked_llm_sets_llm_mode(self) -> None:
        llm_eval = CommunicationContentAidaEvalV1(
            attention=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
            interest=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
            development=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
            action=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
        )
        with (
            patch.dict(os.environ, {'COMM_CONTENT_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': 'test-key'}, clear=False),
            patch('evaluacion.engine.communication_content_evaluator._run_content_llm_openai', return_value=llm_eval),
        ):
            output = evaluate_content_from_transcript(bundle=self._bundle_for_content())
        self.assertEqual(output['runtime_meta']['mode'], 'llm')
        self.assertIsNone(output['runtime_meta']['reason'])

    def test_delivery_flag_off_sets_disabled_flag(self) -> None:
        with patch.dict(os.environ, {'COMM_AUDIO_OPENAI_ENABLED': 'off'}, clear=False):
            _, _, runtime_meta = evaluate_delivery_with_specialized_from_audio_metrics(audio_features=self._audio_features_ready(), transcript_excerpt='x')
        self.assertEqual(runtime_meta['mode'], 'fallback')
        self.assertEqual(runtime_meta['reason'], 'disabled_flag')

    def test_delivery_flag_on_without_api_key_falls_back_missing_openai_api_key(self) -> None:
        with patch.dict(os.environ, {'COMM_AUDIO_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': ''}, clear=False):
            _, _, runtime_meta = evaluate_delivery_with_specialized_from_audio_metrics(audio_features=self._audio_features_ready(), transcript_excerpt='x')
        self.assertEqual(runtime_meta['mode'], 'fallback')
        self.assertEqual(runtime_meta['reason'], 'missing_openai_api_key')

    def test_visual_defaults_to_metadata_mode(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            output = evaluate_communication_visual(self._bundle_for_visual())
        self.assertEqual(output['visual_mode'], 'metadata')
        self.assertEqual(output['runtime_meta']['mode'], 'metadata')
        self.assertIsNone(output['runtime_meta']['reason'])

    def test_visual_llm_v1_enabled_without_api_key_hits_next_barrier(self) -> None:
        from evaluacion.engine.communication_visual_openai_client import CommunicationVisualLlmError

        with (
            patch.dict(os.environ, {'COMM_VISUAL_MODE': 'llm_v1', 'COMM_VISUAL_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': ''}, clear=False),
            patch(
                'evaluacion.engine.communication_evaluators.evaluate_visual_llm_v1_from_features',
                side_effect=CommunicationVisualLlmError(kind='config', message='missing_openai_api_key'),
            ),
        ):
            output = evaluate_communication_visual(self._bundle_for_visual())
        self.assertEqual(output['visual_mode'], 'llm_v1')
        self.assertEqual(output['runtime_meta']['mode'], 'fallback')
        self.assertEqual(output['runtime_meta']['reason'], 'visual_llm_config')

    def test_visual_llm_v1_with_flag_off_keeps_metadata_disabled_flag(self) -> None:
        with patch.dict(os.environ, {'COMM_VISUAL_MODE': 'llm_v1', 'COMM_VISUAL_OPENAI_ENABLED': 'false'}, clear=False):
            output = evaluate_communication_visual(self._bundle_for_visual())
        self.assertEqual(output['runtime_meta']['mode'], 'metadata')
        self.assertEqual(output['runtime_meta']['reason'], 'disabled_flag')

    def test_synthesis_flag_off_sets_disabled_flag(self) -> None:
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_diag_syn',
            content_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'c', 'details': [], 'recommendations': []},
            delivery_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'd', 'details': [], 'recommendations': []},
            visual_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'v', 'details': [], 'recommendations': []},
        )
        with patch.dict(os.environ, {'COMM_SYNTHESIS_OPENAI_ENABLED': '0'}, clear=False):
            _, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        self.assertEqual(meta.mode, 'fallback')
        self.assertEqual(meta.fallback_reason, 'disabled_flag')

    def test_synthesis_flag_on_without_api_key_returns_missing_key_reason(self) -> None:
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_diag_syn_key',
            content_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'c', 'details': [], 'recommendations': []},
            delivery_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'd', 'details': [], 'recommendations': []},
            visual_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'v', 'details': [], 'recommendations': []},
        )
        with patch.dict(os.environ, {'COMM_SYNTHESIS_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': ''}, clear=False):
            _, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        self.assertEqual(meta.mode, 'fallback')
        self.assertEqual(meta.fallback_reason, 'missing_openai_api_key')

    def test_synthesis_flag_on_with_mocked_llm_sets_llm_mode(self) -> None:
        synthesis_input = build_global_synthesis_input(
            evaluation_id='eval_diag_syn_llm',
            content_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'c', 'details': [], 'recommendations': []},
            delivery_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'd', 'details': [], 'recommendations': []},
            visual_output={'score_0_100': 70, 'status_visual': 'mejorable', 'summary': 'v', 'details': [], 'recommendations': []},
        )
        llm_out = {
            'score_global_100': 79,
            'summary_short_2_3_lines': 'Resumen llm.',
            'recommendations': [{'title': 't', 'description': 'd'}],
        }
        with (
            patch.dict(os.environ, {'COMM_SYNTHESIS_OPENAI_ENABLED': 'true', 'OPENAI_API_KEY': 'test-key'}, clear=False),
            patch('evaluacion.engine.communication_synthesis._run_global_synthesis_llm_openai') as run_llm,
        ):
            run_llm.return_value = CommunicationGlobalSynthesisLlmOutputV1(**llm_out)
            _, meta = synthesize_global_communication_feedback(synthesis_input=synthesis_input)
        self.assertEqual(meta.mode, 'llm')
        self.assertIsNone(meta.fallback_reason)

    def test_activation_matrix_defaults_vs_full_llm_vs_missing_key(self) -> None:
        bundle = self._bundle_for_visual()
        bundle.transcript = self._bundle_for_content().transcript
        bundle.audio_features = self._audio_features_ready()

        # Caso A: defaults actuales
        with patch.dict(os.environ, {}, clear=True):
            content = evaluate_communication_content(bundle)
            delivery = evaluate_communication_delivery(bundle)
            visual = evaluate_communication_visual(bundle)
            _, synthesis_meta = evaluate_communication_synthesis(
                bundle=bundle,
                content_output=content,
                delivery_output=delivery,
                visual_output=visual,
            )
        self.assertEqual(content['runtime_meta']['mode'], 'fallback')
        self.assertEqual(content['runtime_meta']['reason'], 'disabled_flag')
        self.assertEqual(delivery['runtime_meta']['mode'], 'fallback')
        self.assertEqual(delivery['runtime_meta']['reason'], 'disabled_flag')
        self.assertEqual(visual['runtime_meta']['mode'], 'metadata')
        self.assertEqual(synthesis_meta['mode'], 'fallback')
        self.assertEqual(synthesis_meta['fallback_reason'], 'disabled_flag')

        # Caso B: full flags ON + API key + LLM mock
        llm_visual_eval = CommunicationVisualEvaluationV1(
            score_0_100=80,
            subscores={'composition': 4, 'stability': 4, 'coverage': 4},
            temporal_findings=[],
            observations=['ok'],
            recommendations=['ok'],
            evidence_frames=['frame_001'],
        )
        llm_visual_batch = CommunicationVisualBatchEvalV2(
            batch_index=1,
            total_batches=1,
            batch_score_1_5=4,
            evidence_sufficiency='high',
            confidence=0.9,
            hand_use_assessment='ok',
            facial_expression_assessment='ok',
            posture_assessment='ok',
            visual_support_assessment='ok',
            strengths=['ok'],
            weaknesses=['ok'],
            limitations=['ok'],
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
                frames_total=6,
                frames_usable=6,
                frames_with_face_visible=6,
                frames_with_hands_visible=6,
                frames_with_upper_body_visible=6,
                frames_blurry=0,
                frames_low_light=0,
            ),
            confidence_reasoning=['ok'],
        )
        llm_visual_final = CommunicationSpecializedDimensionEvalV1(score_1_5=4, label='medio-alto', reason_short='ok')
        with (
            patch.dict(
                os.environ,
                {
                    'COMM_CONTENT_OPENAI_ENABLED': 'true',
                    'COMM_AUDIO_OPENAI_ENABLED': 'true',
                    'COMM_VISUAL_MODE': 'llm_v1',
                    'COMM_VISUAL_OPENAI_ENABLED': 'true',
                    'COMM_SYNTHESIS_OPENAI_ENABLED': 'true',
                    'OPENAI_API_KEY': 'test-key',
                },
                clear=False,
            ),
            patch(
                'evaluacion.engine.communication_content_evaluator._run_content_llm_openai',
                return_value=CommunicationContentAidaEvalV1(
                    attention=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
                    interest=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
                    development=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
                    action=CommunicationContentAidaBlockEvalV1(score_1_3=3, label='correcto', reason_short='ok'),
                ),
            ),
            patch(
                'evaluacion.engine.communication_delivery_evaluator._run_audio_specialized_eval_openai',
                return_value=CommunicationSpecializedDimensionEvalV1(score_1_5=4, label='medio-alto', reason_short='ok'),
            ),
            patch(
                'evaluacion.engine.communication_evaluators.evaluate_visual_llm_v1_from_features',
                return_value=(llm_visual_eval, [llm_visual_batch], llm_visual_final),
            ),
            patch(
                'evaluacion.engine.communication_synthesis._run_global_synthesis_llm_openai',
                return_value=CommunicationGlobalSynthesisLlmOutputV1(
                    score_global_100=80,
                    summary_short_2_3_lines='ok',
                    recommendations=[{'title': 't', 'description': 'd'}],
                ),
            ),
        ):
            content = evaluate_communication_content(bundle)
            delivery = evaluate_communication_delivery(bundle)
            visual = evaluate_communication_visual(bundle)
            _, synthesis_meta = evaluate_communication_synthesis(
                bundle=bundle,
                content_output=content,
                delivery_output=delivery,
                visual_output=visual,
            )
        self.assertEqual(content['runtime_meta']['mode'], 'llm')
        self.assertEqual(delivery['runtime_meta']['mode'], 'llm')
        self.assertEqual(visual['runtime_meta']['mode'], 'llm')
        self.assertEqual(synthesis_meta['mode'], 'llm')

        # Caso C: flags ON sin API key => razones explícitas
        from evaluacion.engine.communication_visual_openai_client import CommunicationVisualLlmError

        with (
            patch.dict(
                os.environ,
                {
                    'COMM_CONTENT_OPENAI_ENABLED': 'true',
                    'COMM_AUDIO_OPENAI_ENABLED': 'true',
                    'COMM_VISUAL_MODE': 'llm_v1',
                    'COMM_VISUAL_OPENAI_ENABLED': 'true',
                    'COMM_SYNTHESIS_OPENAI_ENABLED': 'true',
                    'OPENAI_API_KEY': '',
                },
                clear=False,
            ),
            patch(
                'evaluacion.engine.communication_evaluators.evaluate_visual_llm_v1_from_features',
                side_effect=CommunicationVisualLlmError(kind='config', message='missing_openai_api_key'),
            ),
        ):
            content = evaluate_communication_content(bundle)
            delivery = evaluate_communication_delivery(bundle)
            visual = evaluate_communication_visual(bundle)
            _, synthesis_meta = evaluate_communication_synthesis(
                bundle=bundle,
                content_output=content,
                delivery_output=delivery,
                visual_output=visual,
            )
        self.assertEqual(content['runtime_meta']['reason'], 'missing_openai_api_key')
        self.assertEqual(delivery['runtime_meta']['reason'], 'missing_openai_api_key')
        self.assertEqual(visual['runtime_meta']['reason'], 'visual_llm_config')
        self.assertEqual(synthesis_meta['fallback_reason'], 'missing_openai_api_key')


if __name__ == '__main__':
    unittest.main()
