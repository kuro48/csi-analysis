import unittest
import numpy as np
from worker import approximate, float_ls, float_vmd, uniform_amplitude


class WorkerTests(unittest.TestCase):
    def test_15bpm(self):
        t = np.arange(128) / 2
        signal = 80 * np.sin(2 * np.pi * .25 * t)
        waveform = np.rint(signal).astype(int).tolist()
        self.assertAlmostEqual(float_ls(signal, t)['bpm'], 15, delta=.1)
        self.assertAlmostEqual(float_vmd(signal, 2)['bpm'], 15, delta=1)
        self.assertEqual(approximate(waveform)['peak_bin'], 16)

    def test_zero_is_not_normal(self):
        signal = np.zeros(128)
        self.assertTrue(float_ls(signal, np.arange(128) / 2)['no_signal'])
        self.assertTrue(float_vmd(signal, 2)['no_signal'])
        self.assertFalse(approximate([0] * 128)['in_research_band'])

    def test_range_rejected(self):
        with self.assertRaises(ValueError):
            approximate([101] * 128)

    def test_compact_search_below_nyquist(self):
        t = np.arange(128) / 2
        result = float_ls(np.sin(2 * np.pi * .7 * t), t, max_hz=1.0)
        self.assertAlmostEqual(result['bpm'], 42, delta=.1)

    def test_timestamp_sort_dedup_even_no_extrapolation(self):
        times = np.array([40, 0, 10, 10, 20, 30], dtype=np.int64) * 10**9
        signal = np.ones((6, 2), dtype=complex)
        values, grid, meta = uniform_amplitude(signal, times)
        self.assertEqual(meta['unique_timestamps'], 5)
        self.assertEqual(len(grid) % 2, 0)
        self.assertLessEqual(grid[-1], 40)
        self.assertTrue(np.allclose(values, 1))


if __name__ == '__main__':
    unittest.main()
