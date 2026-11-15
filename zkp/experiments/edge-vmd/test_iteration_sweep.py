import math
from pathlib import Path
import unittest

from iteration_sweep import at_rounds, module


class IterationSweepTests(unittest.TestCase):
    def setUp(self):
        self.reference = module("reference", Path(__file__).resolve().parents[3] /
                                "zkp/scripts/vmd_approx_reference.py")

    def test_four_rounds_matches_original(self):
        waveform = [round(80 * math.sin(2 * math.pi * .25 * t / 2)) for t in range(128)]
        expected = self.reference.vmd_approx(waveform)
        actual = at_rounds(self.reference, waveform, 4)
        self.assertEqual(actual, {key: expected[key] for key in actual})
        self.assertEqual(actual["bpm"], 15)

    def test_restores_rounds_after_success_and_failure(self):
        self.assertEqual(at_rounds(self.reference, [0] * 128, 64)["bpm"], 0)
        self.assertEqual(self.reference.R, 4)
        with self.assertRaises(ValueError):
            at_rounds(self.reference, [101] * 128, 8)
        self.assertEqual(self.reference.R, 4)

    def test_invalid_rounds(self):
        for rounds in (0, -1, 65, 4.5, True):
            with self.assertRaises(ValueError):
                at_rounds(self.reference, [0] * 128, rounds)


if __name__ == "__main__":
    unittest.main()
