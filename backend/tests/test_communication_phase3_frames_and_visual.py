from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from comunicacion.storage import REPOSITORY
from comunicacion.storage.models import RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationFrameWindow,
    CommunicationVisualFeaturesRealV1,
)
from evaluacion.engine.communication_evaluators import evaluate_communication_visual
from evaluacion.engine.communication_frame_extractor import extract_video_frames
from evaluacion.engine.communication_media_processing import CommunicationMediaSource
from evaluacion.engine.communication_service import (
    persist_frame_manifest_artifact,
    persist_visual_evaluation_artifact,
)


class CommunicationPhase3FramesAndVisualTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def test_extract_video_frames_builds_manifest_and_windows(self) -> None:
        with tempfile.TemporaryDirectory(prefix='comm_phase3_') as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / 'input.mp4'
            video_path.write_bytes(b'fake-video')
            recording = RecordingRecord(
                recording_id='rec_phase3',
                attempt_id='att_phase3',
                user_id='iu_phase3',
                session_id='sess_phase3',
                mime_type='video/mp4',
                duration_ms=9_000,
                video_ref=str(video_path),
                created_at=datetime.now(timezone.utc),
            )
            media_source = CommunicationMediaSource(source_ref=str(video_path), local_path=video_path, is_temporary=False)

            def fake_run(command, check, capture_output, text):
                self.assertIn('fps=', ' '.join(command))
                out_dir = Path(command[-1]).parent
                for index in range(1, 6):
                    frame_path = out_dir / f'frame_{index:03d}.jpg'
                    frame_path.write_bytes(b'X' * (9000 + index))

                class _Completed:
                    stdout = ''
                    stderr = ''

                return _Completed()

            with patch('evaluacion.engine.communication_frame_extractor.shutil.which', return_value='/usr/bin/ffmpeg'), patch(
                'evaluacion.engine.communication_frame_extractor.subprocess.run', side_effect=fake_run
            ), patch('evaluacion.engine.communication_frame_extractor._probe_image_dimensions', return_value=(640, 360)):
                manifest = extract_video_frames(media_source=media_source, recording=recording, sample_every_ms=1500, max_frames=6, window_size=2)

        self.assertIsInstance(manifest, CommunicationFrameManifestV1)
        self.assertEqual(len(manifest.frames), 5)
        self.assertEqual(len(manifest.windows), 3)
        self.assertEqual(manifest.frames[0].quality, 'ok')
        self.assertEqual(manifest.frames[0].width, 640)

    def test_visual_evaluator_real_and_artifact_persistence(self) -> None:
        manifest = CommunicationFrameManifestV1(
            source_ref='file:///tmp/video.mp4',
            sampling_policy={'sample_every_ms': 1500, 'max_frames': 12, 'window_size': 4},
            frames=[
                CommunicationFrameSample(frame_id='frame_001', timestamp_ms=0, frame_ref='file:///tmp/f1.jpg', width=640, height=360, byte_size=11000, quality='ok'),
                CommunicationFrameSample(frame_id='frame_002', timestamp_ms=1500, frame_ref='file:///tmp/f2.jpg', width=640, height=360, byte_size=11200, quality='ok'),
                CommunicationFrameSample(frame_id='frame_003', timestamp_ms=3000, frame_ref='file:///tmp/f3.jpg', width=640, height=360, byte_size=9800, quality='ok'),
            ],
            windows=[
                CommunicationFrameWindow(window_id='window_1', start_ms=0, end_ms=3000, frame_ids=['frame_001', 'frame_002', 'frame_003'])
            ],
        )
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=manifest,
            coverage_stats={'expected_frames': 6, 'extracted_frames': 3, 'coverage_ratio': 0.5},
            quality_flags=[],
            explanation='ok',
        )
        bundle = type('Bundle', (), {})()
        bundle.visual_features = visual_features
        bundle.attempt_ref = type('AttemptRef', (), {'recording_id': 'rec_phase3'})()

        evaluation_block = evaluate_communication_visual(type('EvalBundle', (), {'visual_features': visual_features})())
        self.assertEqual(evaluation_block['block_id'], 'visual')
        self.assertIsInstance(evaluation_block['score_0_100'], int)
        self.assertIn('evidence_frames', evaluation_block)

        persist_frame_manifest_artifact(evaluation_id='eval_phase3', bundle=bundle)
        persist_visual_evaluation_artifact(evaluation_id='eval_phase3', bundle=bundle)

        frame_artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_phase3', 'frame_manifest')
        visual_artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_phase3', 'visual_evaluation')
        self.assertEqual(len(frame_artifacts), 1)
        self.assertEqual(len(visual_artifacts), 1)


if __name__ == '__main__':
    unittest.main()
