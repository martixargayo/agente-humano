from __future__ import annotations

import unittest

from evaluacion.engine.communication_visual_sampling import partition_frame_batches


class CommunicationVisualBatchingTests(unittest.TestCase):
    def test_normative_cases(self) -> None:
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(65)))], [30, 35])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(66)))], [30, 30, 6])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(89)))], [30, 30, 29])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(90)))], [30, 30, 30])

    def test_small_cases(self) -> None:
        self.assertEqual([len(chunk) for chunk in partition_frame_batches([])], [])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(1)))], [1])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(5)))], [5])

    def test_case_with_merge(self) -> None:
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(61)))], [30, 31])

    def test_case_without_merge(self) -> None:
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(66)))], [30, 30, 6])
        self.assertEqual([len(chunk) for chunk in partition_frame_batches(list(range(62)), min_tail_batch=2)], [30, 30, 2])

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            partition_frame_batches(list(range(10)), target_batch_size=0)
        with self.assertRaises(ValueError):
            partition_frame_batches(list(range(10)), min_tail_batch=0)


if __name__ == '__main__':
    unittest.main()
