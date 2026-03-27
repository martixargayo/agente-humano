from __future__ import annotations

import unittest
from unittest.mock import patch

from evaluacion.contracts.communication_models import (
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualFrameCoverageSummaryV1,
    CommunicationVisualObservabilityFlagsV1,
)
from evaluacion.engine.communication_visual_batch_runner import (
    build_visual_batch_inputs_from_manifest,
    evaluate_visual_batches_openai,
)


class CommunicationVisualBatchRunnerTests(unittest.TestCase):
    def _manifest(self, frame_count: int) -> CommunicationFrameManifestV1:
        return CommunicationFrameManifestV1(
            source_ref='file:///tmp/video.mp4',
            sampling_policy={'sample_every_ms': 1000},
            frames=[
                CommunicationFrameSample(
                    frame_id=f'frame_{idx:03d}',
                    timestamp_ms=(idx - 1) * 1000,
                    frame_ref=f'file:///tmp/frame_{idx:03d}.jpg',
                    quality='ok',
                )
                for idx in range(1, frame_count + 1)
            ],
            windows=[],
        )

    def test_build_inputs_partitions_batches(self) -> None:
        manifest = self._manifest(66)
        inputs = build_visual_batch_inputs_from_manifest(
            evaluation_id='eval_1',
            recording_id='rec_1',
            video_duration_ms=120_000,
            manifest=manifest,
        )
        self.assertEqual([len(item.frames) for item in inputs], [30, 30, 6])
        self.assertEqual(inputs[0].batch_index, 1)
        self.assertEqual(inputs[-1].total_batches, 3)

    def test_build_inputs_respects_cap_and_full_duration_coverage(self) -> None:
        manifest = self._manifest(180)
        inputs = build_visual_batch_inputs_from_manifest(
            evaluation_id='eval_2',
            recording_id='rec_2',
            video_duration_ms=180_000,
            manifest=manifest,
        )
        flattened = [frame.timestamp_ms for batch in inputs for frame in batch.frames]
        self.assertEqual(len(flattened), 90)
        self.assertGreater(flattened[-1], 89_000)

    def test_evaluate_batches_executes_sequentially(self) -> None:
        manifest = self._manifest(65)
        batch_inputs = build_visual_batch_inputs_from_manifest(
            evaluation_id='eval_3',
            recording_id='rec_3',
            video_duration_ms=90_000,
            manifest=manifest,
        )
        call_order: list[int] = []

        def _fake_run_visual_batch_openai(**kwargs):
            batch_input = kwargs['batch_input']
            call_order.append(batch_input.batch_index)
            return CommunicationVisualBatchEvalV2(
                batch_index=batch_input.batch_index,
                total_batches=batch_input.total_batches,
                batch_score_1_5=4,
                evidence_sufficiency='medium',
                confidence=0.6,
                hand_use_assessment='ok',
                facial_expression_assessment='ok',
                posture_assessment='ok',
                visual_support_assessment='ok',
                strengths=[],
                weaknesses=[],
                limitations=[],
                cited_frame_ids=[frame.frame_id for frame in batch_input.frames[:2]],
                observability_flags=CommunicationVisualObservabilityFlagsV1(
                    hands_not_visible=False,
                    face_partially_visible=False,
                    upper_body_not_visible=False,
                    blur_detected=False,
                    low_light_detected=False,
                    camera_far_distance=False,
                ),
                frame_coverage_summary=CommunicationVisualFrameCoverageSummaryV1(
                    frames_total=len(batch_input.frames),
                    frames_usable=len(batch_input.frames),
                    frames_with_face_visible=len(batch_input.frames),
                    frames_with_hands_visible=len(batch_input.frames) // 2,
                    frames_with_upper_body_visible=len(batch_input.frames),
                    frames_blurry=0,
                    frames_low_light=0,
                ),
                confidence_reasoning=['base'],
            )

        with patch('evaluacion.engine.communication_visual_batch_runner.load_prompt_text', return_value='prompt'), patch(
            'evaluacion.engine.communication_visual_batch_runner.run_visual_batch_openai', side_effect=_fake_run_visual_batch_openai
        ):
            outputs = evaluate_visual_batches_openai(batch_inputs=batch_inputs)

        self.assertEqual(call_order, [1, 2])
        self.assertEqual(len(outputs), 2)


if __name__ == '__main__':
    unittest.main()
