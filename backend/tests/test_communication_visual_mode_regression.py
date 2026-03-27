from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from evaluacion.contracts.communication_models import CommunicationVisualFeaturesRealV1
from evaluacion.engine.communication_evaluators import evaluate_communication_visual


class CommunicationVisualModeRegressionTests(unittest.TestCase):
    def _build_visual_features(self) -> CommunicationVisualFeaturesRealV1:
        from evaluacion.contracts.communication_models import CommunicationFrameManifestV1, CommunicationFrameSample, CommunicationFrameWindow

        frame_manifest = CommunicationFrameManifestV1(
            source_ref='file:///tmp/video.mp4',
            sampling_policy={'sample_every_ms': 1500, 'max_frames': 12, 'window_size': 4},
            frames=[
                CommunicationFrameSample(frame_id='frame_001', timestamp_ms=0, frame_ref='file:///tmp/f1.jpg', quality='ok'),
                CommunicationFrameSample(frame_id='frame_002', timestamp_ms=1500, frame_ref='file:///tmp/f2.jpg', quality='ok'),
                CommunicationFrameSample(frame_id='frame_003', timestamp_ms=3000, frame_ref='file:///tmp/f3.jpg', quality='ok'),
            ],
            windows=[CommunicationFrameWindow(window_id='window_1', start_ms=0, end_ms=3000, frame_ids=['frame_001', 'frame_002'])],
        )
        return CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=frame_manifest,
            coverage_stats={'expected_frames': 3, 'extracted_frames': 3, 'coverage_ratio': 1.0},
            quality_flags=[],
            explanation='ok',
        )

    def test_default_metadata_mode_does_not_call_llm_path(self) -> None:
        bundle = type('Bundle', (), {})()
        bundle.evaluation_id = 'eval_regression'
        bundle.attempt_ref = type('AttemptRef', (), {'recording_id': 'rec_regression'})()
        bundle.recording = type('RecordingMeta', (), {'duration_ms': 10_000})()
        bundle.visual_features = self._build_visual_features()

        with patch.dict(os.environ, {}, clear=True), patch(
            'evaluacion.engine.communication_evaluators.evaluate_visual_llm_v1_from_features'
        ) as llm_mock:
            output = evaluate_communication_visual(bundle)

        self.assertEqual(output['block_id'], 'visual')
        self.assertEqual(output.get('visual_mode'), 'metadata')
        llm_mock.assert_not_called()


if __name__ == '__main__':
    unittest.main()
