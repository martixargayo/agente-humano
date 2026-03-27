from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from evaluacion.contracts.communication_models import (
    CommunicationVisualBatchEvalV2,
    CommunicationVisualFrameCoverageSummaryV1,
    CommunicationVisualObservabilityFlagsV1,
)
from evaluacion.engine.communication_visual_synthesizer import (
    build_visual_synthesis_input,
    run_visual_synthesis_openai,
)


def _batch(batch_index: int) -> CommunicationVisualBatchEvalV2:
    return CommunicationVisualBatchEvalV2(
        batch_index=batch_index,
        total_batches=2,
        batch_score_1_5=4,
        evidence_sufficiency='medium',
        confidence=0.6,
        hand_use_assessment='ok',
        facial_expression_assessment='ok',
        posture_assessment='ok',
        visual_support_assessment='ok',
        strengths=['s'],
        weaknesses=['w'],
        limitations=['l'],
        cited_frame_ids=[f'frame_{batch_index:03d}'],
        observability_flags=CommunicationVisualObservabilityFlagsV1(
            hands_not_visible=False,
            face_partially_visible=False,
            upper_body_not_visible=False,
            blur_detected=False,
            low_light_detected=False,
            camera_far_distance=False,
        ),
        frame_coverage_summary=CommunicationVisualFrameCoverageSummaryV1(
            frames_total=30,
            frames_usable=30,
            frames_with_face_visible=25,
            frames_with_hands_visible=15,
            frames_with_upper_body_visible=24,
            frames_blurry=0,
            frames_low_light=0,
        ),
        confidence_reasoning=['base=0.6'],
    )


class CommunicationVisualSynthesizerTests(unittest.TestCase):
    def test_build_visual_synthesis_input(self) -> None:
        payload = build_visual_synthesis_input(
            evaluation_id='eval_1',
            recording_id='rec_1',
            video_duration_ms=120_000,
            batch_outputs=[_batch(1), _batch(2)],
        )
        self.assertEqual(payload['batch_count'], 2)
        self.assertEqual(payload['batch_outputs'][0]['batch_index'], 1)

    def test_run_visual_synthesis_openai_parses_output(self) -> None:
        fake_response = SimpleNamespace(
            output_text=json.dumps(
                {
                    'global_score_1_5': 4,
                    'label': 'solido',
                    'diagnosis': 'diagnosis',
                    'temporal_consistency': 'medium',
                    'top_strengths': ['s'],
                    'top_weaknesses': ['w'],
                    'recommendations': ['r'],
                    'evidence_frame_ids': ['frame_001'],
                    'confidence': 0.65,
                    'limitations': ['l'],
                    'batch_summaries': [_batch(1).model_dump(mode='json'), _batch(2).model_dump(mode='json')],
                }
            )
        )
        fake_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: fake_response))
        output = run_visual_synthesis_openai(
            evaluation_id='eval_2',
            recording_id='rec_2',
            video_duration_ms=120_000,
            batch_outputs=[_batch(1), _batch(2)],
            client=fake_client,
            max_retries=0,
        )
        self.assertEqual(output.global_score_1_5, 4)


if __name__ == '__main__':
    unittest.main()
