from __future__ import annotations

import unittest

from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
from evaluacion.engine.communication_bundle_builder import build_communication_feedback_input_bundle
from evaluacion.engine.communication_evaluators import evaluate_communication_visual

from datetime import datetime, timezone


class CommunicationVisualPlaceholderTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def test_visual_placeholder_is_explicit_and_pipeline_safe(self) -> None:
        now = datetime.now(timezone.utc)
        REPOSITORY.create_attempt(AttemptRecord(
            attempt_id='att_visual',
            user_id='iu_visual',
            session_id='sess_visual',
            context_id='baseline_current',
            status='uploaded',
            recording_id='rec_visual',
            created_at=now,
            updated_at=now,
        ))
        REPOSITORY.attach_recording(RecordingRecord(
            recording_id='rec_visual',
            attempt_id='att_visual',
            user_id='iu_visual',
            session_id='sess_visual',
            mime_type='video/webm',
            duration_ms=8000,
            video_ref='client-temp://sess_visual/att_visual/1.webm',
            created_at=now,
        ))

        bundle = build_communication_feedback_input_bundle(evaluation_id='eval_visual', attempt_id='att_visual')
        visual = evaluate_communication_visual(bundle)

        self.assertEqual(bundle.visual_features.status, 'placeholder')
        self.assertIsNone(bundle.visual_features.score_visual_0_100)
        self.assertEqual(visual['status_visual'], 'placeholder')
        self.assertIn('Evaluación visual degradada', visual['summary'])
