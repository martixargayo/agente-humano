from __future__ import annotations

import unittest

from evaluacion.engine.communication_visual_sampling import (
    build_candidate_timestamps_1fps,
    select_uniform_indices,
    select_uniform_timestamps_from_candidates,
)


class CommunicationVisualSamplingTests(unittest.TestCase):
    def test_candidate_timestamps_short_durations(self) -> None:
        self.assertEqual(build_candidate_timestamps_1fps(500), [0])
        self.assertEqual(build_candidate_timestamps_1fps(999), [0])
        self.assertEqual(build_candidate_timestamps_1fps(1000), [0])

    def test_candidate_timestamps_full_seconds(self) -> None:
        out_65 = build_candidate_timestamps_1fps(65_000)
        self.assertEqual(len(out_65), 65)
        self.assertEqual(out_65[0], 0)
        self.assertEqual(out_65[-1], 64_000)

        out_90 = build_candidate_timestamps_1fps(90_000)
        self.assertEqual(len(out_90), 90)
        self.assertEqual(out_90[-1], 89_000)

        out_90_5 = build_candidate_timestamps_1fps(90_500)
        self.assertEqual(len(out_90_5), 90)
        self.assertEqual(out_90_5[-1], 89_000)

        out_180 = build_candidate_timestamps_1fps(180_000)
        self.assertEqual(len(out_180), 180)
        self.assertEqual(out_180[-1], 179_000)

    def test_select_uniform_indices_within_limit(self) -> None:
        self.assertEqual(select_uniform_indices(1, max_frames=90), [0])
        self.assertEqual(select_uniform_indices(90, max_frames=90), list(range(90)))

    def test_select_uniform_from_180_seconds_covers_whole_duration(self) -> None:
        candidates = build_candidate_timestamps_1fps(180_000)
        selected = select_uniform_timestamps_from_candidates(candidates, max_frames=90)

        self.assertEqual(len(selected), 90)
        self.assertEqual(selected[0], 0)
        self.assertEqual(selected, sorted(selected))
        self.assertEqual(len(set(selected)), 90)

        # Validates it does not only select the first 90 seconds.
        self.assertGreater(selected[-1], 89_000)
        self.assertGreaterEqual(selected[-1], 170_000)

    def test_invalid_inputs_raise(self) -> None:
        with self.assertRaises(ValueError):
            build_candidate_timestamps_1fps(-1)
        with self.assertRaises(ValueError):
            select_uniform_indices(0)


if __name__ == '__main__':
    unittest.main()
