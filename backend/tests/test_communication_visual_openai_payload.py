from __future__ import annotations

import unittest
from unittest.mock import patch

from evaluacion.contracts.communication_models import (
    CommunicationVisualBatchEvalInputV1,
    CommunicationVisualBatchFrameRefV1,
    CommunicationVisualSamplingStrategyV1,
)
from evaluacion.engine.communication_visual_openai_client import _build_multimodal_input_for_batch


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


if __name__ == '__main__':
    unittest.main()
