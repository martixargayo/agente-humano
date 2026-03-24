from __future__ import annotations

import unittest
from datetime import datetime, timezone

from comunicacion.storage import AttemptNotFoundError, AttemptRecord, REPOSITORY, RecordingRecord


class ComunicacionRecordingRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        REPOSITORY.create_attempt(
            AttemptRecord(
                attempt_id='att_repo',
                user_id='iu_repo',
                session_id='sess_repo',
                context_id='baseline_current',
                status='draft',
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )

    def test_attach_and_get_recording_for_existing_attempt(self) -> None:
        record = RecordingRecord(
            recording_id='rec_repo',
            attempt_id='att_repo',
            user_id='iu_repo',
            session_id='sess_repo',
            mime_type='video/webm',
            duration_ms=1000,
            video_ref='storage://tmp/rec_repo/original.webm',
            poster_frame_ref='storage://tmp/rec_repo/poster.jpg',
            capture_meta={'width': 1280},
            created_at=datetime.now(timezone.utc),
        )
        REPOSITORY.attach_recording(record)
        stored = REPOSITORY.get_recording('rec_repo')

        self.assertIsNotNone(stored)
        self.assertEqual(stored.recording_id, 'rec_repo')
        self.assertEqual(stored.attempt_id, 'att_repo')
        self.assertEqual(stored.video_ref, 'storage://tmp/rec_repo/original.webm')

    def test_attach_recording_to_missing_attempt_fails(self) -> None:
        record = RecordingRecord(
            recording_id='rec_missing',
            attempt_id='att_missing',
            user_id='iu_repo',
            session_id='sess_repo',
            mime_type='video/webm',
            duration_ms=1000,
            video_ref='storage://tmp/rec_missing/original.webm',
            created_at=datetime.now(timezone.utc),
        )
        with self.assertRaises(AttemptNotFoundError):
            REPOSITORY.attach_recording(record)
