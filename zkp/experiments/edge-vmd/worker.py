#!/usr/bin/env python3
"""Shared-waveform LS/VMD experiments; raw/intermediate data stay on the edge."""

import argparse
import contextlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import secrets
import statistics
import subprocess
import tempfile
import time

import numpy as np
from scipy.signal import lombscargle
from sklearn.decomposition import PCA

HERE = Path(__file__).resolve().parent
EDGE = Path('/home/infonetworking/csi-zkp')
LS_PACKAGE = EDGE / 'packages/lomb_scargle_e2e'
CLI = LS_PACKAGE / 'vendor/runtime/node_modules/snarkjs/build/cli.cjs'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


bp = module('breathing', HERE / 'vendor/breathing_pipeline.py')
reference = module('vmd_reference', HERE / 'vendor/vmd_approx_reference.py')


def uniform_amplitude(csi, stamps):
    stamps = np.asarray(stamps, dtype=np.int64)
    order = np.argsort(stamps, kind='stable')
    stamps = stamps[order]
    keep = np.concatenate(([True], np.diff(stamps) > 0))
    stamps = stamps[keep]
    amplitude = np.abs(csi[order][keep])
    if len(stamps) < 4 or not np.all(np.isfinite(amplitude)):
        raise ValueError('Need finite CSI and at least four distinct timestamps')
    times = (stamps - stamps[0]).astype(np.float64) / 1e9
    if times[-1] < 30 or times[-1] > 120:
        raise ValueError('This bounded experiment supports 30..120 second captures')
    grid = np.arange(int(math.floor(times[-1] * bp.FS)) + 1) / bp.FS
    if grid.size % 2:
        grid = grid[:-1]  # VMD drops an odd last sample; explicitly share the same even grid.
    uniform = np.column_stack([np.interp(grid, times, amplitude[:, i]) for i in range(amplitude.shape[1])])
    gaps = np.diff(times)
    metadata = dict(original_frames=int(csi.shape[0]), unique_timestamps=len(times),
                    original_series=int(csi.shape[1]), duration_seconds=float(times[-1]),
                    mean_packet_rate_hz=float((len(times) - 1) / times[-1]),
                    interval_cv=float(np.std(gaps) / np.mean(gaps)), max_gap_seconds=float(gaps.max()),
                    uniform_fs_hz=bp.FS, uniform_samples=len(grid),
                    resampling='amplitude linear interpolation within recorded time range; even length, no extrapolation')
    return uniform, grid, metadata


def prepare(source):
    started = time.perf_counter()
    # The edge prover's loader selects eight series. For this comparison use
    # the backend's batched loader, which retains the complete modal CSI width.
    with contextlib.redirect_stdout(io.StringIO()):
        csi, stamps = bp.load_csi_matrix_with_timestamps(str(source))
    amplitude, grid, metadata = uniform_amplitude(csi, stamps)
    del csi
    with contextlib.redirect_stdout(io.StringIO()):
        selected, indices, _ = bp.select_subcarriers_by_snr(amplitude, bp.FS, bp.LOWCUT, bp.HIGHCUT, bp.N_SELECT)
        filtered = bp.bandpass_filter(selected, bp.FS, bp.LOWCUT, bp.HIGHCUT, 4)
        components = PCA(n_components=3, svd_solver='full').fit_transform(filtered)
        pc, pc_index, _ = bp.select_respiration_pc(components, bp.FS, bp.LOWCUT, bp.HIGHCUT)
    if not np.all(np.isfinite(pc)):
        raise ValueError('Non-finite preprocessed waveform')
    metadata.update(selected_series=len(indices), selected_pc_0based=int(pc_index),
                    preprocess_seconds=time.perf_counter() - started,
                    pca='3 components, full SVD, shared FFT-band-ratio PC selection',
                    filter='existing fourth-order Butterworth + filtfilt, 0.1..1 Hz')
    return pc, grid, metadata


def float_vmd(signal, fs):
    if float(np.max(np.abs(signal - np.mean(signal)))) < 1e-12:
        return dict(bpm=None, in_research_band=False, no_signal=True)
    with contextlib.redirect_stdout(io.StringIO()):
        _, _, best = bp.estimate_breathing_rate_by_vmd_global_peak(
            signal, fs, 6, 22, bp.VMD_K, bp.VMD_ALPHA, bp.VMD_TAU, bp.VMD_DC, bp.VMD_INIT, bp.VMD_TOL)
    return dict(bpm=float(best['global_peak_bpm']), in_research_band=bool(best['is_valid']),
                selected_mode=int(best['mode_index']), no_signal=False)


def float_ls(signal, times, max_hz=1.5):
    if float(np.max(np.abs(signal - np.mean(signal)))) < 1e-12:
        return dict(bpm=None, in_research_band=False, no_signal=True)
    # A 2 Hz uniform signal has Nyquist frequency 1 Hz: do not search its aliases.
    frequencies = np.linspace(0.05, max_hz, 1000, endpoint=max_hz != 1.0)
    power = lombscargle(times, signal, 2 * np.pi * frequencies, precenter=True, normalize=True, floating_mean=True)
    if not np.all(np.isfinite(power)):
        raise ValueError('Non-finite Lomb-Scargle spectrum')
    global_index = int(np.argmax(power))
    band = np.flatnonzero((frequencies * 60 >= 6) & (frequencies * 60 <= 22))
    band_index = int(band[np.argmax(power[band])])
    bpm = float(60 * frequencies[global_index])
    return dict(bpm=bpm, in_band_peak_bpm=float(60 * frequencies[band_index]),
                in_research_band=bool(6 <= bpm <= 22), no_signal=False)


def approximate(waveform):
    result = reference.vmd_approx(waveform)
    return dict(bpm=float(result['bpm']), peak_bin=result['peak_bin'], selected_mode=result['selected_mode'],
                in_research_band=result['is_normal'], no_signal=result['peak_bin'] == 0)


def measurements(function, repetitions=3):
    function()  # One unmeasured warmup per method/input; same preprocessed waveform.
    rows = []
    for _ in range(repetitions):
        start = time.perf_counter()
        result = function()
        rows.append(dict(seconds=time.perf_counter() - start, result=result))
    if any(r['result'] != rows[0]['result'] for r in rows):
        raise RuntimeError('Algorithm result not reproducible')
    seconds = [r['seconds'] for r in rows]
    return dict(result=rows[0]['result'], trials=rows, repetitions=repetitions,
                median_seconds=statistics.median(seconds), min_seconds=min(seconds), max_seconds=max(seconds))


def command(args, output):
    start = time.perf_counter()
    # communicate() drains pipes and waits for completion, avoiding timed wait polling.
    completed = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
    duration = time.perf_counter() - start
    output.write_text(completed.stdout)
    if completed.returncode:
        raise RuntimeError(f'Command failed: {output.name} (exit {completed.returncode})')
    return duration


def prove(waveform, destination):
    expected = approximate(waveform)
    destination.mkdir(exist_ok=False)
    artifacts = HERE / 'artifacts'
    with tempfile.TemporaryDirectory(prefix='vmd-private-', dir=str(EDGE / 'cache')) as temporary:
        work = Path(temporary)
        inputs = dict(waveform=waveform, commitmentNonce=str(secrets.randbits(248)), parentCommitment='0')
        (work / 'input.json').write_text(json.dumps(inputs))
        witness_s = command(['node', str(artifacts / 'generate_witness.js'), str(artifacts / 'csi_vmd_approx.wasm'),
                             str(work / 'input.json'), str(work / 'witness.wtns')], destination / 'witness.log')
        proof_s = command(['node', str(CLI), 'groth16', 'prove', str(artifacts / 'csi_vmd_approx_final.zkey'),
                           str(work / 'witness.wtns'), str(destination / 'proof.json'), str(destination / 'public.json')],
                          destination / 'prove.log')
        verify_s = command(['node', str(CLI), 'groth16', 'verify', str(artifacts / 'verification_key.json'),
                            str(destination / 'public.json'), str(destination / 'proof.json')], destination / 'verify.log')
        values = [int(x) for x in json.loads((destination / 'public.json').read_text())]
        if len(values) != 5 or values[:3] != [int(expected['in_research_band']), expected['peak_bin'], expected['selected_mode']] or values[4] != 0:
            raise RuntimeError('VMD public outputs do not match integer reference')
        if 'OK!' not in (destination / 'verify.log').read_text():
            raise RuntimeError('Verification success marker missing')
        # Negative check against the original proof, not a regenerated proof.
        changed = [str(x) for x in values]
        changed[0] = str(1 - values[0])
        (work / 'tampered.json').write_text(json.dumps(changed))
        negative = subprocess.run(['node', str(CLI), 'groth16', 'verify', str(artifacts / 'verification_key.json'),
                                   str(work / 'tampered.json'), str(destination / 'proof.json')], capture_output=True, text=True, timeout=30)
        (destination / 'negative.log').write_text(negative.stdout + negative.stderr)
        if negative.returncode == 0 or 'Invalid proof' not in negative.stdout + negative.stderr:
            raise RuntimeError('Tampered verdict not rejected')
    return dict(verified=True, matches_integer_reference=True, tampered_verdict_rejected=True, public_signal_count=5,
                parent_commitment='0', chain_linked=False, scope='128-sample preprocessed waveform only; raw CSI preprocessing not proved',
                witness_seconds=witness_s, proof_seconds=proof_s, verify_seconds=verify_s, result=expected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path)
    parser.add_argument('--synthetic-hz', type=float)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (args.source is None) == (args.synthetic_hz is None):
        parser.error('Choose source or synthetic-hz')
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.source:
        pc, times, metadata = prepare(args.source)
    else:
        times = np.arange(6400) / 100
        pc = 80 * np.sin(2 * np.pi * args.synthetic_hz * times)
        metadata = dict(synthetic_hz=args.synthetic_hz, true_bpm=60 * args.synthetic_hz,
                        uniform_fs_hz=100, uniform_samples=len(pc), preprocess_seconds=0)
    waveform = bp.prepare_vmd_approx_input(pc)['waveform']
    metadata['approximation_padded_samples'] = max(0, 128 - int(math.ceil(len(pc) / 50)))
    metadata['approximation_truncated_samples'] = max(0, int(math.ceil(len(pc) / 50)) - 128)
    metadata['approximation_fs_hz'] = 2
    metadata['approximation_samples'] = 128
    results = dict(metadata=metadata,
                   float_ls=measurements(lambda: float_ls(pc, times)),
                   float_vmd=measurements(lambda: float_vmd(pc, 100)),
                   compact_float_ls=measurements(lambda: float_ls(np.asarray(waveform, dtype=float), np.arange(128) / 2, max_hz=1.0)),
                   compact_float_vmd=measurements(lambda: float_vmd(np.asarray(waveform, dtype=float), 2)),
                   compact_integer_vmd=measurements(lambda: approximate(waveform)))
    results['vmd_proof'] = prove(waveform, args.output / 'proof')
    results['ground_truth_available'] = args.synthetic_hz is not None
    (args.output / 'summary.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
