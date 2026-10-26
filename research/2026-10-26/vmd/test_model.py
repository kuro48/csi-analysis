"""Regression against existing integer reference, independent of the sweep implementation."""
import importlib.util
import unittest
from pathlib import Path

import numpy as np
from model import decompose

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('production_reference',ROOT/'zkp/scripts/vmd_approx_reference.py')
production=importlib.util.module_from_spec(spec);spec.loader.exec_module(production)

class IntegerReferenceTest(unittest.TestCase):
    def test_matches_existing_reference(self):
        rng=np.random.default_rng(20261026)
        inputs=[[0]*128]+[rng.integers(-100,101,128).tolist() for _ in range(10)]
        for wave in inputs:
            actual=decompose(wave);expected=production.vmd_approx(wave)
            for key in ['peak_bin','selected_mode','is_normal','centers']:
                self.assertEqual(actual[key],expected[key])
            self.assertEqual(actual['spectra'],[[list(v) for v in m] for m in expected['spectra']])

    def test_tones(self):
        for hz,expected in [(.25,16),(.5,32),(.8,51)]:
            wave=np.rint(80*np.sin(2*np.pi*hz*np.arange(128)/2)).astype(int)
            self.assertEqual(decompose(wave)['peak_bin'],expected)

    def test_invalid_inputs(self):
        for wave in [[0]*127,[101]*128,[.1]*128]:
            with self.assertRaises(ValueError):decompose(wave)

if __name__=='__main__':unittest.main()
