from __future__ import annotations

import unittest

from pydantic import ValidationError

from evaluacion.contracts.communication_models import (
    CommunicationVisualBatchEvalInputV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualBatchFrameRefV1,
    CommunicationVisualFinalEvalV1,
    CommunicationVisualFrameCoverageSummaryV1,
    CommunicationVisualObservabilityFlagsV1,
    CommunicationVisualSamplingStrategyV1,
)


class CommunicationVisualContractsTests(unittest.TestCase):
    def test_sampling_strategy_defaults(self) -> None:
        strategy = CommunicationVisualSamplingStrategyV1()
        self.assertEqual(strategy.mode, 'uniform_1fps_capped_90')
        self.assertEqual(strategy.candidate_fps, 1)
        self.assertEqual(strategy.max_frames, 90)
        self.assertEqual(strategy.batch_target, 30)
        self.assertEqual(strategy.tail_merge_threshold, 6)

    def test_batch_eval_input_model(self) -> None:
        payload = CommunicationVisualBatchEvalInputV1(
            evaluation_id='eval_1',
            recording_id='rec_1',
            batch_index=1,
            total_batches=3,
            video_duration_ms=180_000,
            frames=[
                CommunicationVisualBatchFrameRefV1(
                    frame_id='frame_001',
                    timestamp_ms=0,
                    frame_ref='file:///tmp/frame_001.jpg',
                )
            ],
            rubric={'hand_use': '1-5'},
        )
        self.assertEqual(payload.frames[0].detail, 'low')

    def test_batch_eval_v2_is_strict_and_validates_ranges(self) -> None:
        flags = CommunicationVisualObservabilityFlagsV1(
            hands_not_visible=False,
            face_partially_visible=True,
            upper_body_not_visible=False,
            blur_detected=False,
            low_light_detected=False,
            camera_far_distance=False,
        )
        coverage = CommunicationVisualFrameCoverageSummaryV1(
            frames_total=30,
            frames_usable=25,
            frames_with_face_visible=24,
            frames_with_hands_visible=12,
            frames_with_upper_body_visible=20,
            frames_blurry=2,
            frames_low_light=1,
        )

        out = CommunicationVisualBatchEvalV2(
            batch_index=1,
            total_batches=3,
            batch_score_1_5=4,
            evidence_sufficiency='medium',
            confidence=0.62,
            hand_use_assessment='ok',
            facial_expression_assessment='ok',
            posture_assessment='ok',
            visual_support_assessment='ok',
            strengths=['s1'],
            weaknesses=['w1'],
            limitations=['l1'],
            cited_frame_ids=['frame_001'],
            observability_flags=flags,
            frame_coverage_summary=coverage,
            confidence_reasoning=['base=0.62'],
        )
        self.assertEqual(out.schema_version, 'communication_visual_batch_eval.v2')

        with self.assertRaises(ValidationError):
            CommunicationVisualBatchEvalV2(
                batch_index=1,
                total_batches=3,
                batch_score_1_5=6,
                evidence_sufficiency='medium',
                confidence=0.62,
                hand_use_assessment='ok',
                facial_expression_assessment='ok',
                posture_assessment='ok',
                visual_support_assessment='ok',
                strengths=[],
                weaknesses=[],
                limitations=[],
                cited_frame_ids=[],
                observability_flags=flags,
                frame_coverage_summary=coverage,
                confidence_reasoning=[],
            )

        with self.assertRaises(ValidationError):
            CommunicationVisualBatchEvalV2.model_validate({
                'batch_index': 1,
                'total_batches': 3,
                'batch_score_1_5': 4,
                'evidence_sufficiency': 'medium',
                'confidence': 0.62,
                'hand_use_assessment': 'ok',
                'facial_expression_assessment': 'ok',
                'posture_assessment': 'ok',
                'visual_support_assessment': 'ok',
                'strengths': [],
                'weaknesses': [],
                'limitations': [],
                'cited_frame_ids': [],
                'observability_flags': flags.model_dump(),
                'frame_coverage_summary': coverage.model_dump(),
                'confidence_reasoning': [],
                'unexpected': True,
            })

    def test_final_eval_model(self) -> None:
        summary = CommunicationVisualBatchEvalV2(
            batch_index=1,
            total_batches=1,
            batch_score_1_5=3,
            evidence_sufficiency='low',
            confidence=0.4,
            hand_use_assessment='low',
            facial_expression_assessment='low',
            posture_assessment='low',
            visual_support_assessment='low',
            strengths=[],
            weaknesses=['w'],
            limitations=['l'],
            cited_frame_ids=['frame_001'],
            observability_flags=CommunicationVisualObservabilityFlagsV1(
                hands_not_visible=True,
                face_partially_visible=False,
                upper_body_not_visible=True,
                blur_detected=False,
                low_light_detected=False,
                camera_far_distance=False,
            ),
            frame_coverage_summary=CommunicationVisualFrameCoverageSummaryV1(
                frames_total=10,
                frames_usable=5,
                frames_with_face_visible=3,
                frames_with_hands_visible=0,
                frames_with_upper_body_visible=4,
                frames_blurry=0,
                frames_low_light=0,
            ),
            confidence_reasoning=['cap'],
        )

        final = CommunicationVisualFinalEvalV1(
            global_score_1_5=3,
            label='mejorable',
            diagnosis='dx',
            temporal_consistency='medium',
            top_strengths=[],
            top_weaknesses=['w'],
            recommendations=['r'],
            evidence_frame_ids=['frame_001'],
            confidence=0.41,
            limitations=['limit'],
            batch_summaries=[summary],
        )
        self.assertEqual(final.schema_version, 'communication_visual_final_eval.v1')


if __name__ == '__main__':
    unittest.main()
