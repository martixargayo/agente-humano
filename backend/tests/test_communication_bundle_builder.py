from __future__ import annotations

import unittest
from unittest.mock import patch

from comunicacion.storage import AttemptRecord, REPOSITORY, RecordingRecord
from evaluacion.contracts.communication_models import CommunicationTranscriptRealV1, CommunicationTranscriptSegment
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

    def test_uses_real_transcript_when_stt_provider_is_available(self) -> None:
        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id='att_test_real',
            user_id='iu_a',
            session_id='sess_a',
            context_id='baseline_current',
            status='uploaded',
            recording_id='rec_test_real',
            created_at=now,
            updated_at=now,
        )
        recording = RecordingRecord(
            recording_id='rec_test_real',
            attempt_id='att_test_real',
            user_id='iu_a',
            session_id='sess_a',
            mime_type='video/webm',
            duration_ms=12000,
            video_ref='file:///tmp/nonexistent.webm',
            capture_meta={'provisional_client_ref': True},
            created_at=now,
        )
        REPOSITORY.create_attempt(attempt)
        REPOSITORY.attach_recording(recording)

        transcript_real = CommunicationTranscriptRealV1(
            provider='mock_word_timed_stt',
            language='es',
            full_text='Hola, esta es una transcripción real de prueba.',
            segments=[CommunicationTranscriptSegment(segment_index=1, start_ms=0, end_ms=1500, text='Hola, esta es una transcripción real de prueba.')],
            confidence_global=0.95,
            quality_flags=[],
            explanation='mock',
        )
        with patch('evaluacion.engine.communication_bundle_builder.build_real_transcript', return_value=transcript_real):
            bundle = build_communication_feedback_input_bundle(
                evaluation_id='eval_test_real',
                attempt_id='att_test_real',
            )
        self.assertEqual(bundle.transcript.status, 'ready')
        self.assertEqual(bundle.transcript.provider, 'mock_word_timed_stt')
        self.assertTrue(bundle.transcript.full_text.startswith('Hola'))
