from __future__ import annotations

import threading
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from comunicacion.storage import REPOSITORY
from comunicacion.storage.models import AttemptRecord, RecordingRecord
from evaluacion.engine.communication_service import (
    get_communication_evaluation_report,
    get_communication_evaluation_status,
    run_communication_evaluation_job_inline_for_tests,
)


class CommunicationParallelPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        REPOSITORY._attempts.clear()
        REPOSITORY._recordings.clear()
        REPOSITORY._artifacts.clear()
        if hasattr(REPOSITORY, '_communication_eval_jobs'):
            REPOSITORY._communication_eval_jobs.clear()
        if hasattr(REPOSITORY, '_communication_eval_reports'):
            REPOSITORY._communication_eval_reports.clear()

        now = datetime.now(timezone.utc)
        attempt = AttemptRecord(
            attempt_id='att_parallel',
            user_id='iu_parallel',
            session_id='sess_parallel',
            context_id='baseline_current',
            status='submitted',
            recording_id='rec_parallel',
            created_at=now,
            updated_at=now,
        )
        recording = RecordingRecord(
            recording_id='rec_parallel',
            attempt_id='att_parallel',
            user_id='iu_parallel',
            session_id='sess_parallel',
            mime_type='video/webm',
            duration_ms=14000,
            video_ref='client-temp://sess_parallel/att_parallel/video.webm',
            capture_meta={'provisional_client_ref': True},
            created_at=now,
        )
        REPOSITORY.create_attempt(attempt)
        REPOSITORY.attach_recording(recording)

    def test_parallel_branches_overlap_and_synthesis_waits_for_three(self) -> None:
        timestamps: dict[str, float] = {}
        lock = threading.Lock()
        barrier = threading.Barrier(3, timeout=3)

        def _mark(name: str, phase: str) -> None:
            with lock:
                timestamps[f'{name}_{phase}'] = time.perf_counter()

        def _content(bundle):  # type: ignore[no-untyped-def]
            _mark('content', 'start')
            barrier.wait()
            time.sleep(0.08)
            _mark('content', 'end')
            return {'block_id': 'contenido', 'title': 'Contenido', 'status_visual': 'correcto', 'score_0_100': 80, 'summary': 'ok', 'details': [], 'recommendations': []}

        def _delivery(bundle):  # type: ignore[no-untyped-def]
            _mark('delivery', 'start')
            barrier.wait()
            time.sleep(0.1)
            _mark('delivery', 'end')
            return {'block_id': 'delivery', 'title': 'Delivery', 'status_visual': 'correcto', 'score_0_100': 78, 'summary': 'ok', 'details': [], 'recommendations': []}

        def _visual(bundle):  # type: ignore[no-untyped-def]
            _mark('visual', 'start')
            barrier.wait()
            time.sleep(0.09)
            _mark('visual', 'end')
            return {'block_id': 'visual', 'title': 'Visual', 'status_visual': 'correcto', 'score_0_100': 76, 'summary': 'ok', 'details': [], 'recommendations': [], 'evidence_frames': []}

        def _synthesis(**kwargs):  # type: ignore[no-untyped-def]
            _mark('synthesis', 'start')
            return {
                'schema_version': 'communication_global_synthesis_output.v1',
                'global_score_0_100': 79,
                'global_diagnosis': 'ok',
                'top_strengths': [],
                'priority_improvements': [],
                'action_plan': [],
                'friendly_summary': 'ok',
                'consistency_notes': [],
            }

        with (
            patch('evaluacion.engine.communication_service.evaluate_communication_content', side_effect=_content),
            patch('evaluacion.engine.communication_service.evaluate_communication_delivery', side_effect=_delivery),
            patch('evaluacion.engine.communication_service.evaluate_communication_visual', side_effect=_visual),
            patch('evaluacion.engine.communication_service.evaluate_communication_synthesis', side_effect=_synthesis),
        ):
            run_communication_evaluation_job_inline_for_tests(evaluation_id='eval_parallel_1', attempt_id='att_parallel')

        self.assertLess(timestamps['content_start'], timestamps['delivery_end'])
        self.assertLess(timestamps['delivery_start'], timestamps['visual_end'])
        self.assertLess(timestamps['visual_start'], timestamps['content_end'])
        latest_branch_end = max(timestamps['content_end'], timestamps['delivery_end'], timestamps['visual_end'])
        self.assertGreaterEqual(timestamps['synthesis_start'], latest_branch_end)

    def test_branch_failure_is_degraded_without_failing_whole_job(self) -> None:
        def _content(bundle):  # type: ignore[no-untyped-def]
            raise RuntimeError('content exploded')

        with patch('evaluacion.engine.communication_service.evaluate_communication_content', side_effect=_content):
            run_communication_evaluation_job_inline_for_tests(evaluation_id='eval_parallel_2', attempt_id='att_parallel')

        status = get_communication_evaluation_status(evaluation_id='eval_parallel_2')
        self.assertEqual(status.status, 'completed')
        self.assertEqual(status.stage, 'completed')

        report = get_communication_evaluation_report(evaluation_id='eval_parallel_2')
        content_block = next(block for block in report.block_cards if block.block_id == 'contenido')
        self.assertEqual(content_block.status_visual, 'placeholder')
        self.assertIn('degradada', content_block.summary.lower())


if __name__ == '__main__':
    unittest.main()
