"""Reproducible VMD K/R sweep on common raw-CSI windows and synthetic controls."""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import lombscargle
from vmdpy import VMD

from model import decompose, INITIAL_CENTERS

HERE = Path(__file__).resolve().parent
MODES = [1, 2, 3, 4, 5, 8]
ROUNDS = [1, 2, 4, 8, 16, 32]


def controls():
    t = np.arange(128) / 2
    for bpm in [9, 12, 15, 18, 21]:
        for kind in ['clean', 'noise', 'strong_interferer']:
            for seed in range(3):
                rng = np.random.default_rng(20261026 + seed)
                y = np.sin(2 * np.pi * bpm / 60 * t + seed * .4)
                if kind != 'clean':
                    y += rng.normal(0, .35, 128)
                if kind == 'strong_interferer':
                    y += 1.6 * np.sin(2 * np.pi * .7 * t + .8)
                y -= y.mean()
                x = np.rint(y / np.max(np.abs(y)) * 100).astype(int)
                yield f'synthetic_{kind}_{bpm}_{seed}', x, float(bpm), kind


def baselines(x):
    t = np.arange(128) / 2
    freq = np.arange(.05, .990001, .00025)
    power = lombscargle(t, x - x.mean(), 2 * np.pi * freq)
    band = (freq >= .1) & (freq <= 22 / 60)
    modes, _, omega = VMD(x.astype(float) - x.mean(), 2000, 0, 5, 0, 1, 1e-7)
    mp = np.abs(np.fft.rfft(modes - modes.mean(axis=1, keepdims=True), axis=1)) ** 2
    mp[:, 0] = 0
    peaks = mp.argmax(axis=1)
    global_mode = np.unravel_index(np.argmax(mp), mp.shape)[0]
    ratios = mp.max(axis=1) / np.maximum(mp.sum(axis=1), 1e-20)
    eligible = np.flatnonzero((peaks * 120 / 128 >= 6) & (peaks * 120 / 128 <= 22))
    choice = eligible[np.argmax(ratios[eligible])] if len(eligible) else np.argmax(ratios)
    fft = np.abs(np.fft.rfft(x)) ** 2
    return dict(ls_global_bpm=float(freq[np.argmax(power)] * 60),
                ls_band_bpm=float(freq[band][np.argmax(power[band])] * 60),
                dft_global_bpm=float((np.argmax(fft[1:64]) + 1) * 120 / 128),
                standard_vmd_global_bpm=float(peaks[global_mode] * 120 / 128),
                standard_vmd_band_priority_bpm=float(peaks[choice] * 120 / 128),
                standard_vmd_iterations=len(omega))


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(include_real=True, include_synthetic=True, output_dir=HERE):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = list(controls()) if include_synthetic else []
    for path in (sorted((HERE.parent / "common/synthetic").glob("*.npz")) if include_synthetic else []):
        data = np.load(path)
        cases.append((path.stem, data["signal128"], float(data["target_bpm"]), "synthetic_csi"))
    if include_real:
        for path in sorted((HERE.parent / 'common/windows').glob('csi_*.npz')):
            data = np.load(path)
            cases.append((path.stem, data['signal128'], None, 'real'))
    rows = []
    baseline_rows = []
    for name, x, gt, kind in cases:
        x = np.asarray(x, dtype=np.int64)
        base = baselines(x)
        baseline_rows.append(dict(case=name, kind=kind, ground_truth_bpm=gt, **base))
        for k in MODES:
            for r in ROUNDS:
                # Timing is Python integer-reference execution, never proof generation.
                elapsed = []
                for repeat in range(3):
                    start = time.perf_counter();res = decompose(x, k, r);elapsed.append(time.perf_counter() - start)
                row = dict(case=name, kind=kind, modes=k, iterations=r,
                           initial_centers=json.dumps(INITIAL_CENTERS[:k]),
                           bpm=res['bpm'], selected_mode=res['selected_mode'],
                           final_centers=json.dumps(res['centers']),
                           band_priority_bpm=res['band_priority_bpm'],
                           reference_compute_median_ms=float(np.median(elapsed) * 1000),
                           ground_truth_bpm=gt,
                           abs_error_gt_bpm=abs(res['bpm'] - gt) if gt is not None else None,
                           band_priority_abs_error_gt_bpm=abs(res['band_priority_bpm'] - gt) if gt is not None else None,
                           abs_difference_ls_band_bpm=abs(res['bpm'] - base['ls_band_bpm']),
                           abs_difference_ls_global_bpm=abs(res['bpm'] - base['ls_global_bpm']), **base)
                rows.append(row)
        print(name, 'completed', flush=True)
    write_csv(output_dir / 'sweep.csv', rows)
    write_csv(output_dir / 'baselines.csv', baseline_rows)
    baseline_aggregate=[]
    for kind in sorted(set(row['kind'] for row in baseline_rows)):
        group=[row for row in baseline_rows if row['kind']==kind]
        for method in ['ls_global_bpm','ls_band_bpm','dft_global_bpm','standard_vmd_global_bpm','standard_vmd_band_priority_bpm']:
            errors=[abs(row[method]-row['ls_band_bpm' if kind=='real' else 'ground_truth_bpm']) for row in group]
            baseline_aggregate.append(dict(kind=kind,method=method,n=len(group),
              mean_absolute_difference_bpm=float(np.mean(errors)),within_1bpm=float(np.mean(np.asarray(errors)<=1)),
              reference='LS band (not ground truth)' if kind=='real' else 'synthetic target ground truth'))
    (output_dir / 'baseline_aggregate.json').write_text(json.dumps(baseline_aggregate,indent=2))
    aggregate=[]
    for kind in sorted(set(row['kind'] for row in rows)):
        for k in MODES:
            for r in ROUNDS:
                group=[x for x in rows if x['kind']==kind and x['modes']==k and x['iterations']==r]
                a=dict(kind=kind,modes=k,iterations=r,n=len(group),
                       mean_abs_difference_ls_band_bpm=np.mean([x['abs_difference_ls_band_bpm'] for x in group]),
                       mean_abs_difference_ls_global_bpm=np.mean([x['abs_difference_ls_global_bpm'] for x in group]),
                       agreement_ls_band_within_1bpm=np.mean([x['abs_difference_ls_band_bpm']<=1 for x in group]),
                       median_compute_ms=np.median([x['reference_compute_median_ms'] for x in group]),
                       gt_mae_bpm=np.mean([x['abs_error_gt_bpm'] for x in group]) if kind!='real' else None,
                       gt_within_1bpm=np.mean([x['abs_error_gt_bpm']<=1 for x in group]) if kind!='real' else None,
                       band_priority_gt_mae_bpm=np.mean([x['band_priority_abs_error_gt_bpm'] for x in group]) if kind!='real' else None)
                aggregate.append(a)
    write_csv(output_dir / 'aggregate.csv', aggregate)
    (output_dir / 'aggregate.json').write_text(json.dumps(aggregate, indent=2))
    (output_dir / 'metadata.json').write_text(json.dumps(dict(modes=MODES,iterations=ROUNDS,
      initial_centers=INITIAL_CENTERS,case_count=len(cases),real_count=sum(c[3]=='real' for c in cases),
      synthetic_count=sum(c[3]!='real' for c in cases),sample_rate_hz=2,samples=128,
      input_windows={"real_and_synthetic_csi":{"observed_seconds":48,"padded_samples":32},
                     "direct_synthetic_controls":{"observed_seconds":64,"padded_samples":0}},
      reference='Production integer VMD update/selection, parameterized K/R',
      timing='3 executions per cell; Python reference only; preprocessing/compile/witness/proof excluded',
      ls='SciPy Lomb-Scargle on same quantized 128-sample waveform; .05..99Hz step .00025Hz, band .1..22/60Hz',
      standard_vmd='vmdpy 0.2: K5 alpha2000 tau0 DC0 init1 tol1e-7 on same 2Hz waveform (not production 100Hz pipeline)',
      ground_truth='Synthetic injected target only. Raw data has no paired physiological ground truth identified.'),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    selection=p.add_mutually_exclusive_group()
    selection.add_argument('--synthetic-only',action='store_true')
    selection.add_argument('--real-only',action='store_true',help='Only the eight main Raw windows; exclude both synthetic sources')
    p.add_argument('--output-dir',type=Path,default=HERE,help='Destination for sweep, aggregates, baselines and metadata')
    a=p.parse_args()
    run(include_real=not a.synthetic_only, include_synthetic=not a.real_only, output_dir=a.output_dir)
