#!/usr/bin/env python3
"""Sequential, non-destructive baseline measurements of the deployed prover."""

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import statistics
import subprocess
import time

ROOT = Path('/home/infonetworking/csi-zkp')
PACKAGE = ROOT / 'packages/lomb_scargle_e2e'
CASES = [
    ('A', 'csi_20261005_115619.csi', 'real_20261005_115619.json'),
    ('B', 'csi_20261005_115523.csi', 'real_20261005_115523.json'),
    ('C', 'csi_20260907_185130.csi', 'real_20260907_185130.json'),
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def distribution(values):
    return dict(n=len(values), median=statistics.median(values), mean=statistics.mean(values),
                min=min(values), max=max(values), sample_sd=statistics.stdev(values) if len(values) > 1 else None)


def stable_signals(data):
    signals = data['publicSignals']
    if len(signals) != 69 or str(signals[1]) not in ('0', '1'):
        raise ValueError('Unexpected public signal layout')
    if data['result']['isNormal'] != bool(int(signals[1])):
        raise ValueError('Display verdict does not match public signal')
    return [str(value) for value in signals[1:]]  # Randomized commitment excluded.


def summarize(rows):
    results = []
    for case, filename, _ in CASES:
        selected = [r for r in rows if r['case'] == case and not r['warmup']]
        if selected:
            results.append(dict(case=case, source=filename, runs=len(selected),
                                total_seconds=distribution([r['total_seconds'] for r in selected]),
                                max_rss_gib=distribution([r['max_rss_kib'] / 1048576 for r in selected]),
                                reverify_seconds=distribution([r['reverify_seconds'] for r in selected]),
                                all_verified=all(r['verified'] for r in selected),
                                all_match_baseline=all(r['matches_baseline'] for r in selected),
                                isNormal=selected[0]['isNormal']))
    return results


def snapshot():
    return dict(time=dt.datetime.now().astimezone().isoformat(), loadavg=Path('/proc/loadavg').read_text().strip(),
                meminfo=Path('/proc/meminfo').read_text(),
                picoscenes=subprocess.run(['ps', '-C', 'PicoScenes', '-o', 'pid,etime,%cpu,%mem,comm'],
                                          capture_output=True, text=True).stdout,
                node=subprocess.check_output(['node', '--version'], text=True).strip(),
                python=subprocess.check_output(['python3', '--version'], text=True).strip())


def run(command, log, timeout=300):
    started = time.perf_counter()
    with log.open('w') as output:
        output.write('ARGV ' + json.dumps(command) + '\n')
        output.flush()
        with subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True) as process:
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
    elapsed = time.perf_counter() - started
    if status != 0:
        raise RuntimeError(f'Command failed ({status}): {log.name}')
    return elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--repetitions', type=int, default=5)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.run_id) or not 2 <= args.repetitions <= 20:
        parser.error('Invalid run ID or repetitions (allowed 2..20)')
    os.umask(0o077)
    os.environ.update(DELETE_SOURCE_AFTER_PROOF='0', LC_ALL='C')
    lock = (ROOT / 'benchmark.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    out = ROOT / 'results/benchmarks' / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    for name in ('logs', 'proofs', 'timings'):
        (out / name).mkdir()
    start = snapshot()
    available = int(re.search(r'MemAvailable:\s+(\d+)', start['meminfo'])[1])
    if available < 8 * 1024 * 1024:
        raise RuntimeError('At least 8 GiB MemAvailable required before benchmark')
    sources = {case: Path('/home/infonetworking/csi_data/main') / filename for case, filename, _ in CASES}
    before = {case: sha256(path) for case, path in sources.items()}
    inventory = {Path(row['path']).name: row['sha256'] for row in json.loads((ROOT / 'results/csi_inventory.json').read_text())}
    if any(before[case] != inventory[path.name] for case, path in sources.items()):
        raise RuntimeError('Source changed since environment setup')
    baseline = {case: json.loads((ROOT / 'results' / original).read_text()) for case, _, original in CASES}
    for data in baseline.values():
        stable_signals(data)
    artifacts = {str(p.relative_to(PACKAGE)): sha256(p) for p in sorted((PACKAGE / 'artifacts').iterdir()) if p.is_file()}
    protocol = dict(run_id=args.run_id, purpose='Current-circuit baseline, not a comparison with a new circuit or VMD',
                    repetitions_per_case=args.repetitions, warmups_per_case=1, parallel_proofs=1,
                    order='Warmup A,B,C; measured rounds rotate A,B,C / B,C,A / C,A,B',
                    source_hashes=before, artifact_hashes=artifacts, node_options=os.environ.get('NODE_OPTIONS'),
                    script_sha256=sha256(Path(__file__)), source_preservation=True,
                    timing='perf_counter around unchanged prove.sh including process startup and GNU time wrapper; excludes independent reverify',
                    memory='GNU time max RSS of command/children, not sum of simultaneous processes or OS-wide peak',
                    caveats=['Warm cache, no cache flushing', 'Existing PicoScenes process is not stopped',
                             'Phase timers from prove.sh have integer-second resolution',
                             'No ground-truth respiratory rate or clinical accuracy evaluation',
                             'Commitment/proof randomness excluded from deterministic comparison',
                             'No new circuit, algorithm, package or tool installed'])
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    rows = []
    summary = dict(status='running', protocol=protocol, before=start, trials=rows)
    try:
        run(['python3', str(PACKAGE / 'bin/verify_manifest.py')], out / 'logs/manifest-before.txt')
        for case, _, original in CASES:
            run([str(PACKAGE / 'bin/verify.sh'), str(ROOT / 'results' / original)], out / f'logs/baseline-{case}.txt')
        for round_index in range(args.repetitions + 1):
            warmup = round_index == 0
            shift = max(0, round_index - 1) % len(CASES)
            order = CASES[shift:] + CASES[:shift]
            for case, filename, _ in order:
                label = f'{"warmup" if warmup else "run"}-{round_index:02d}-{case}'
                proof = out / 'proofs' / f'{label}.json'
                timing = out / 'timings' / f'{label}.txt'
                log = out / 'logs' / f'{label}.txt'
                total = run(['/usr/bin/time', '-f', '%e %M', '-o', str(timing),
                             str(PACKAGE / 'bin/prove.sh'), str(sources[case]), str(proof)], log)
                wall, rss = timing.read_text().strip().split()
                data = json.loads(proof.read_text())
                matches = stable_signals(data) == stable_signals(baseline[case])
                verifylog = out / 'logs' / f'{label}-reverify.txt'
                reverify = run([str(PACKAGE / 'bin/verify.sh'), str(proof)], verifylog)
                if 'OK!' not in verifylog.read_text() or not matches:
                    raise RuntimeError(f'Verification/reproducibility mismatch: {label}')
                phases = re.search(r'witness_seconds=(\d+) proof_seconds=(\d+) verify_seconds=(\d+)', log.read_text())
                if phases is None:
                    raise RuntimeError(f'Missing phase timings: {label}')
                row = dict(label=label, case=case, source=filename, warmup=warmup, round=round_index,
                           total_seconds=total, gnu_wall_seconds=float(wall), max_rss_kib=int(rss),
                           witness_seconds_integer=int(phases[1]), proof_seconds_integer=int(phases[2]),
                           verify_seconds_integer=int(phases[3]), reverify_seconds=reverify,
                           verified=True, matches_baseline=matches, isNormal=data['result']['isNormal'],
                           public_signal_count=len(data['publicSignals']), proof_bytes=proof.stat().st_size)
                rows.append(row)
                (out / 'progress.json').write_text(json.dumps(rows, indent=2))
                print(json.dumps(row), flush=True)
        run(['python3', str(PACKAGE / 'bin/verify_manifest.py')], out / 'logs/manifest-after.txt')
        summary['status'] = 'passed'
    except BaseException as exc:
        summary.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        after = {case: sha256(path) for case, path in sources.items()}
        summary.update(after=snapshot(), sources_unchanged=before == after, source_hashes_after=after,
                       results=summarize(rows), completed_trials=len(rows))
        if not summary['sources_unchanged']:
            summary['status'] = 'failed'
        (out / 'summary.json').write_text(json.dumps(summary, indent=2))
        if rows:
            with (out / 'trials.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
        print('SUMMARY ' + str(out / 'summary.json'), flush=True)
    if summary['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
