from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from evaluacion.contracts.communication_models import CommunicationVisualBatchEvalInputV1, CommunicationVisualBatchFrameRefV1
from evaluacion.engine.communication_visual_openai_client import (
    CommunicationVisualLlmError,
    _build_multimodal_input_for_batch,
    run_visual_batch_openai,
)


def _valid_batch_output() -> dict[str, object]:
    return {
        'batch_index': 1,
        'total_batches': 1,
        'batch_score_1_5': 4,
        'evidence_sufficiency': 'medium',
        'confidence': 0.62,
        'hand_use_assessment': 'ok',
        'facial_expression_assessment': 'ok',
        'posture_assessment': 'ok',
        'visual_support_assessment': 'ok',
        'strengths': ['s'],
        'weaknesses': ['w'],
        'limitations': ['l'],
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
            'frames_total': 6,
            'frames_usable': 6,
            'frames_with_face_visible': 6,
            'frames_with_hands_visible': 4,
            'frames_with_upper_body_visible': 6,
            'frames_blurry': 0,
            'frames_low_light': 0,
        },
        'confidence_reasoning': ['base=0.62'],
    }


class CommunicationVisualOpenAiClientTests(unittest.TestCase):
    def _batch_input(self) -> CommunicationVisualBatchEvalInputV1:
        frames = [
            CommunicationVisualBatchFrameRefV1(
                frame_id=f'frame_{idx:03d}',
                timestamp_ms=(idx - 1) * 1000,
                frame_ref=f'file:///tmp/frame_{idx:03d}.jpg',
            )
            for idx in range(1, 7)
        ]
        return CommunicationVisualBatchEvalInputV1(
            evaluation_id='eval_1',
            recording_id='rec_1',
            batch_index=1,
            total_batches=1,
            video_duration_ms=12_000,
            frames=frames,
            rubric={'hand_use': '1-5'},
        )

    def test_build_multimodal_input_uses_data_urls_and_low_detail(self) -> None:
        batch_input = self._batch_input()
        with patch(
            'evaluacion.engine.communication_visual_openai_client._load_and_normalize_frame_as_data_url',
            return_value=('data:image/jpeg;base64,AAAA', 120_000),
        ):
            payload, summary = _build_multimodal_input_for_batch(batch_input=batch_input, developer_prompt='prompt')

        self.assertEqual(payload[0]['role'], 'developer')
        user_content = payload[1]['content']
        image_items = [item for item in user_content if item.get('type') == 'input_image']
        self.assertEqual(len(image_items), 6)
        self.assertTrue(all(item.get('detail') == 'low' for item in image_items))
        self.assertEqual(summary['frames_usable'], 6)

    def test_run_visual_batch_openai_parses_structured_output(self) -> None:
        batch_input = self._batch_input()
        fake_response = SimpleNamespace(output_text=json.dumps(_valid_batch_output()))
        fake_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: fake_response))
        with patch(
            'evaluacion.engine.communication_visual_openai_client._build_multimodal_input_for_batch',
            return_value=([{'role': 'developer', 'content': 'x'}, {'role': 'user', 'content': []}], {'frames_usable': 6}),
        ):
            out = run_visual_batch_openai(
                batch_input=batch_input,
                developer_prompt='prompt',
                model='gpt-4.1-mini',
                timeout_s=5.0,
                max_retries=1,
                client=fake_client,
            )
        self.assertEqual(out.batch_score_1_5, 4)

    def test_run_visual_batch_openai_retries_transient_error(self) -> None:
        batch_input = self._batch_input()
        fake_response = SimpleNamespace(output_text=json.dumps(_valid_batch_output()))
        calls = {'n': 0}

        def _create(**_: object) -> object:
            calls['n'] += 1
            if calls['n'] == 1:
                raise RuntimeError('timeout while requesting provider')
            return fake_response

        fake_client = SimpleNamespace(responses=SimpleNamespace(create=_create))
        with patch(
            'evaluacion.engine.communication_visual_openai_client._build_multimodal_input_for_batch',
            return_value=([{'role': 'developer', 'content': 'x'}, {'role': 'user', 'content': []}], {'frames_usable': 6}),
        ):
            out = run_visual_batch_openai(
                batch_input=batch_input,
                developer_prompt='prompt',
                model='gpt-4.1-mini',
                timeout_s=5.0,
                max_retries=1,
                client=fake_client,
            )
        self.assertEqual(out.batch_index, 1)
        self.assertEqual(calls['n'], 2)

    def test_run_visual_batch_openai_raises_on_schema_error(self) -> None:
        batch_input = self._batch_input()
        fake_response = SimpleNamespace(output_text='not-json')
        fake_client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: fake_response))
        with patch(
            'evaluacion.engine.communication_visual_openai_client._build_multimodal_input_for_batch',
            return_value=([{'role': 'developer', 'content': 'x'}, {'role': 'user', 'content': []}], {'frames_usable': 6}),
        ):
            with self.assertRaises(CommunicationVisualLlmError):
                run_visual_batch_openai(
                    batch_input=batch_input,
                    developer_prompt='prompt',
                    model='gpt-4.1-mini',
                    timeout_s=5.0,
                    max_retries=0,
                    client=fake_client,
                )

    def test_build_multimodal_input_raises_on_serialization_failure(self) -> None:
        batch_input = self._batch_input()
        with patch(
            'evaluacion.engine.communication_visual_openai_client._load_and_normalize_frame_as_data_url',
            side_effect=CommunicationVisualLlmError(kind='serialization', message='boom'),
        ):
            with self.assertRaises(CommunicationVisualLlmError):
                _build_multimodal_input_for_batch(batch_input=batch_input, developer_prompt='prompt')


if __name__ == '__main__':
    unittest.main()
