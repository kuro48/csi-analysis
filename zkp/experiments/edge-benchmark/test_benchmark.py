import unittest

from benchmark import distribution, stable_signals, summarize


class BenchmarkTests(unittest.TestCase):
    def test_statistics(self):
        stats = distribution([1, 2, 3, 4, 5])
        self.assertEqual(stats['median'], 3)
        self.assertEqual(stats['n'], 5)
        self.assertAlmostEqual(stats['sample_sd'], 1.5811388300841898)

    def test_commitment_is_not_part_of_reproducibility_check(self):
        original = {'publicSignals': ['123', '1'] + ['0'] * 67, 'result': {'isNormal': True}}
        changed = {'publicSignals': ['999', '1'] + ['0'] * 67, 'result': {'isNormal': True}}
        self.assertEqual(stable_signals(original), stable_signals(changed))
        changed['publicSignals'][2] = '1'
        self.assertNotEqual(stable_signals(original), stable_signals(changed))

    def test_invalid_display_rejected(self):
        with self.assertRaises(ValueError):
            stable_signals({'publicSignals': ['0'] * 69, 'result': {'isNormal': True}})

    def test_warmup_excluded(self):
        base = dict(case='A', max_rss_kib=1048576, reverify_seconds=0.2, verified=True,
                    matches_baseline=True, isNormal=True)
        rows = [dict(base, warmup=True, total_seconds=999), dict(base, warmup=False, total_seconds=10),
                dict(base, warmup=False, total_seconds=12)]
        result = summarize(rows)[0]
        self.assertEqual(result['runs'], 2)
        self.assertEqual(result['total_seconds']['median'], 11)
        self.assertEqual(result['max_rss_gib']['median'], 1)


if __name__ == '__main__':
    unittest.main()
