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
            return ({
                'score_global_100': 79,
                'summary_short_2_3_lines': 'Resumen breve de prueba.',
                'recommendations': [],
            }, {
                'mode': 'llm',
                'fallback_reason': None,
                'detail': None,
            })

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

    def test_delivery_and_visual_failures_are_degraded(self) -> None:
        def _delivery(bundle):  # type: ignore[no-untyped-def]
            raise RuntimeError('delivery exploded')

        def _visual(bundle):  # type: ignore[no-untyped-def]
            raise RuntimeError('visual exploded')

        with (
            patch('evaluacion.engine.communication_service.evaluate_communication_delivery', side_effect=_delivery),
            patch('evaluacion.engine.communication_service.evaluate_communication_visual', side_effect=_visual),
        ):
            run_communication_evaluation_job_inline_for_tests(evaluation_id='eval_parallel_3', attempt_id='att_parallel')

        report = get_communication_evaluation_report(evaluation_id='eval_parallel_3')
        delivery_block = next(block for block in report.block_cards if block.block_id == 'delivery')
        visual_block = next(block for block in report.block_cards if block.block_id == 'visual')
        self.assertEqual(delivery_block.status_visual, 'placeholder')
        self.assertEqual(visual_block.status_visual, 'placeholder')

    def test_timeout_in_branch_degrades_that_branch(self) -> None:
        def _visual(bundle):  # type: ignore[no-untyped-def]
            time.sleep(0.2)
            return {'block_id': 'visual', 'title': 'Visual', 'status_visual': 'correcto', 'score_0_100': 75, 'summary': 'ok', 'details': [], 'recommendations': [], 'evidence_frames': []}

        with (
            patch('evaluacion.engine.communication_service.evaluate_communication_visual', side_effect=_visual),
            patch('evaluacion.engine.communication_service._PARALLEL_ANALYSIS_TIMEOUT_SECONDS', 0.05),
        ):
            run_communication_evaluation_job_inline_for_tests(evaluation_id='eval_parallel_4', attempt_id='att_parallel')

        report = get_communication_evaluation_report(evaluation_id='eval_parallel_4')
        visual_block = next(block for block in report.block_cards if block.block_id == 'visual')
        self.assertEqual(visual_block.status_visual, 'placeholder')
        self.assertIn('degradada', visual_block.summary.lower())

    def test_assembler_runs_after_synthesis(self) -> None:
        timestamps: dict[str, float] = {}

        def _synthesis(**kwargs):  # type: ignore[no-untyped-def]
            timestamps['synthesis_start'] = time.perf_counter()
            time.sleep(0.03)
            timestamps['synthesis_end'] = time.perf_counter()
            return ({
                'score_global_100': 70,
                'summary_short_2_3_lines': 'Resumen breve de prueba.',
                'recommendations': [],
            }, {
                'mode': 'llm',
                'fallback_reason': None,
                'detail': None,
            })

        def _assemble(**kwargs):  # type: ignore[no-untyped-def]
            timestamps['assembler_start'] = time.perf_counter()
            self.assertGreaterEqual(timestamps['assembler_start'], timestamps['synthesis_end'])
            from evaluacion.engine.communication_report_assembler import assemble_communication_report

            return assemble_communication_report(**kwargs)

        with (
            patch('evaluacion.engine.communication_service.evaluate_communication_synthesis', side_effect=_synthesis),
            patch('evaluacion.engine.communication_service.assemble_communication_report', side_effect=_assemble),
        ):
            run_communication_evaluation_job_inline_for_tests(evaluation_id='eval_parallel_5', attempt_id='att_parallel')


if __name__ == '__main__':
    unittest.main()
