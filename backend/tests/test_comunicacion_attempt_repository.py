from __future__ import annotations

import unittest
from datetime import datetime, timezone

from comunicacion.storage import AttemptRecord, REPOSITORY


class ComunicacionAttemptRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()

    def test_create_and_get_attempt_keeps_initial_status_and_context(self) -> None:
        record = AttemptRecord(
            attempt_id='att_test_1',
            user_id='iu_1',
            session_id='sess_1',
            context_id='baseline_current',
            status='draft',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        REPOSITORY.create_attempt(record)
        stored = REPOSITORY.get_attempt('att_test_1')

        self.assertIsNotNone(stored)
        self.assertEqual(stored.attempt_id, 'att_test_1')
        self.assertEqual(stored.status, 'draft')
        self.assertEqual(stored.context_id, 'baseline_current')
