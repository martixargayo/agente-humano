from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from comunicacion.storage import REPOSITORY
from comunicacion.storage.models import AttemptRecord, RecordingRecord
from evaluacion.contracts.communication_models import (
    CommunicationFrameManifestV1,
    CommunicationFrameSample,
    CommunicationSpecializedDimensionEvalV1,
    CommunicationVisualBatchEvalV2,
    CommunicationVisualFeaturesRealV1,
    CommunicationVisualFrameCoverageSummaryV1,
    CommunicationVisualObservabilityFlagsV1,
)
from evaluacion.engine.communication_evaluators import evaluate_communication_visual
from evaluacion.engine.communication_service import persist_visual_batch_eval_artifacts, persist_visual_llm_final_artifact


class CommunicationVisualPipelineE2ELlmMockTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()

    def _bundle(self):
        manifest = CommunicationFrameManifestV1(
            source_ref='file:///tmp/video.mp4',
            sampling_policy={'sample_every_ms': 1000},
            frames=[
                CommunicationFrameSample(
                    frame_id=f'frame_{idx:03d}',
                    timestamp_ms=(idx - 1) * 1000,
                    frame_ref=f'file:///tmp/f{idx}.jpg',
                    quality='ok',
                )
                for idx in range(1, 13)
            ],
            windows=[],
        )
        visual_features = CommunicationVisualFeaturesRealV1(
            status='ready',
            frame_manifest=manifest,
            coverage_stats={'expected_frames': 12, 'extracted_frames': 12, 'coverage_ratio': 1.0},
            quality_flags=[],
            explanation='ok',
        )
        bundle = type('Bundle', (), {})()
        bundle.evaluation_id = 'eval_e2e_llm'
        bundle.attempt_ref = type('AttemptRef', (), {'recording_id': 'rec_e2e_llm'})()
        bundle.recording = type('RecordingMeta', (), {'duration_ms': 12_000})()
        bundle.visual_features = visual_features
        return bundle

    def test_llm_mode_success_and_artifact_persistence(self) -> None:
        bundle = self._bundle()

        batch_output = CommunicationVisualBatchEvalV2(
            batch_index=1,
            total_batches=1,
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
                frames_total=12,
                frames_usable=12,
                frames_with_face_visible=10,
                frames_with_hands_visible=8,
                frames_with_upper_body_visible=10,
                frames_blurry=0,
                frames_low_light=0,
            ),
            confidence_reasoning=['base=0.6'],
        )
        final_output = CommunicationSpecializedDimensionEvalV1(
            score_1_5=4,
            label='medio-alto',
            reason_short='Tu gesticulación acompaña bien tu mensaje y puedes sostenerla mejor.',
        )

        with patch.dict(os.environ, {'COMMUNICATION_FORCE_SAFE_MODE': 'false'}), patch(
            'evaluacion.engine.communication_visual_evaluator.evaluate_visual_batches_openai',
            return_value=[batch_output],
        ), patch(
            'evaluacion.engine.communication_visual_evaluator.run_visual_synthesis_openai',
            return_value=final_output,
        ):
            visual_output = evaluate_communication_visual(bundle)

        self.assertEqual(visual_output['block_id'], 'visual')
        self.assertEqual(visual_output['visual_mode'], 'llm_v1')
        self.assertTrue(visual_output['llm_batch_evaluations'])
        self.assertTrue(visual_output['llm_final_evaluation'])

        recording = RecordingRecord(
            recording_id='rec_e2e_llm',
            attempt_id='att_e2e_llm',
            user_id='iu',
            session_id='sess',
            mime_type='video/mp4',
            duration_ms=12_000,
            video_ref='file:///tmp/video.mp4',
            created_at=datetime.now(timezone.utc),
        )
        REPOSITORY.create_attempt(
            AttemptRecord(
                attempt_id='att_e2e_llm',
                user_id='iu',
                session_id='sess',
                context_id='baseline_current',
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        REPOSITORY.attach_recording(recording)

        persist_visual_batch_eval_artifacts(evaluation_id='eval_e2e_llm', bundle=bundle, visual_output=visual_output)
        persist_visual_llm_final_artifact(evaluation_id='eval_e2e_llm', bundle=bundle, visual_output=visual_output)

        batch_artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_e2e_llm', 'visual_batch_eval')
        final_artifacts = REPOSITORY.list_artifacts_for_recording_and_kind('rec_e2e_llm', 'visual_llm_final')
        self.assertEqual(len(batch_artifacts), 1)
        self.assertEqual(len(final_artifacts), 1)


if __name__ == '__main__':
    unittest.main()
