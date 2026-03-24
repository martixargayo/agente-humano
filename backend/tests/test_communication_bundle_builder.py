from __future__ import annotations

import unittest

from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
from evaluacion.engine.communication_bundle_builder import build_communication_feedback_input_bundle

from datetime import datetime, timezone


class CommunicationBundleBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

    def test_builds_bundle_with_domain_context_and_honest_placeholders(self) -> None:
        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id='att_test',
            user_id='iu_a',
            session_id='sess_a',
            context_id='baseline_current',
            status='uploaded',
            recording_id='rec_test',
            created_at=now,
            updated_at=now,
        )
        recording = RecordingRecord(
            recording_id='rec_test',
            attempt_id='att_test',
            user_id='iu_a',
            session_id='sess_a',
            mime_type='video/webm',
            duration_ms=12000,
            video_ref='client-temp://sess_a/att_test/1.webm',
            capture_meta={'provisional_client_ref': True},
            created_at=now,
        )
        REPOSITORY.create_attempt(attempt)
        REPOSITORY.attach_recording(recording)

        bundle = build_communication_feedback_input_bundle(evaluation_id='eval_test', attempt_id='att_test')

        self.assertEqual(bundle.domain_context.domain, 'comunicacion')
        self.assertEqual(bundle.domain_context.context_id, 'baseline_current')
        self.assertEqual(bundle.attempt_ref.recording_id, 'rec_test')
        self.assertEqual(bundle.transcript.status, 'placeholder')
        self.assertEqual(bundle.audio_features.status, 'placeholder')
        self.assertEqual(bundle.visual_features.status, 'placeholder')
        self.assertIn('No existe transcripción automática real', bundle.transcript.explanation)
        self.assertIn('No hay extracción acústica real', bundle.audio_features.explanation)
        self.assertIn('MVP actual', bundle.visual_features.summary)
