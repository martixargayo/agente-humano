from __future__ import annotations

import unittest
from unittest.mock import patch

from evaluacion.contracts.communication_models import (
    CommunicationVisualBatchEvalInputV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualBatchFrameRefV1,
    CommunicationVisualSamplingStrategyV1,
)
from evaluacion.engine.communication_visual_openai_client import _build_multimodal_input_for_batch, run_visual_batch_openai


class CommunicationVisualOpenaiPayloadTests(unittest.TestCase):
    def _batch(self, total_frames: int) -> CommunicationVisualBatchEvalInputV1:
        return CommunicationVisualBatchEvalInputV1(
            evaluation_id='eval_payload',
            recording_id='rec_payload',
            batch_index=1,
            total_batches=1,
            video_duration_ms=8_000,
            sampling_strategy=CommunicationVisualSamplingStrategyV1(max_frames=90, batch_target=30, tail_merge_threshold=6),
            frames=[
                CommunicationVisualBatchFrameRefV1(
                    frame_id=f'frame_{idx:03d}',
                    timestamp_ms=idx * 1500,
                    frame_ref=f'file:///tmp/frame_{idx:03d}.jpg',
                )
                for idx in range(1, total_frames + 1)
            ],
            rubric={'hand_use': 'x'},
        )

    def test_short_batch_with_five_frames_is_accepted_when_all_are_usable(self) -> None:
        batch = self._batch(total_frames=5)
        with patch(
            'evaluacion.engine.communication_visual_openai_client._load_and_normalize_frame_as_data_url',
            return_value=('data:image/jpeg;base64,AAA', 1024),
        ):
            message_input, summary = _build_multimodal_input_for_batch(batch_input=batch, developer_prompt='prompt')

        self.assertEqual(summary['frames_total'], 5)
        self.assertEqual(summary['frames_usable'], 5)
        self.assertEqual(summary['min_usable_frames_required'], 3)
        self.assertEqual(len(message_input), 2)



    def test_visual_batch_schema_has_all_properties_in_required(self) -> None:
        schema = CommunicationVisualBatchEvalV2.model_json_schema()
        self.assertEqual(set(schema.get('properties', {}).keys()), set(schema.get('required', [])))
        self.assertIn('schema_version', schema.get('required', []))

    def test_run_visual_batch_openai_valid_batch_does_not_raise_schema_error(self) -> None:
        batch = self._batch(total_frames=8)

        class _FakeResponses:
            def __init__(self) -> None:
                self.captured_schema = None

            def create(self, **kwargs):
                self.captured_schema = kwargs['text']['format']['schema']
                payload = {
                    'schema_version': 'communication_visual_batch_eval.v2',
                    'batch_index': 1,
                    'total_batches': 1,
                    'batch_score_1_5': 4,
                    'evidence_sufficiency': 'high',
                    'confidence': 0.8,
                    'hand_use_assessment': 'ok',
                    'facial_expression_assessment': 'ok',
                    'posture_assessment': 'ok',
                    'visual_support_assessment': 'ok',
                    'strengths': ['ok'],
                    'weaknesses': ['ok'],
                    'limitations': ['ok'],
                    'cited_frame_ids': ['frame_001'],
                    'observability_flags': {
                        'hands_not_visible': False,
                        'face_partially_visible': False,
                        'upper_body_not_visible': False,
                        'blur_detected': False,
                        'low_light_detected': False,
                        'camera_far_distance': False,
                    },
                    'frame_coverage_summary': {
                        'frames_total': 8,
                        'frames_usable': 8,
                        'frames_with_face_visible': 8,
                        'frames_with_hands_visible': 8,
                        'frames_with_upper_body_visible': 8,
                        'frames_blurry': 0,
                        'frames_low_light': 0,
                    },
                    'confidence_reasoning': ['ok'],
                }
                return type('Resp', (), {'output_text': __import__('json').dumps(payload)})()

        fake_responses = _FakeResponses()
        fake_client = type('FakeClient', (), {'responses': fake_responses})()
        with patch(
            'evaluacion.engine.communication_visual_openai_client._load_and_normalize_frame_as_data_url',
            return_value=('data:image/jpeg;base64,AAA', 1024),
        ):
            result = run_visual_batch_openai(
                batch_input=batch,
                developer_prompt='prompt',
                model='gpt-4.1-mini',
                timeout_s=20.0,
                max_retries=0,
                client=fake_client,
            )

        self.assertEqual(result.batch_index, 1)
        schema = fake_responses.captured_schema
        self.assertEqual(set(schema.get('properties', {}).keys()), set(schema.get('required', [])))
        self.assertIn('schema_version', schema.get('required', []))

if __name__ == '__main__':
    unittest.main()
