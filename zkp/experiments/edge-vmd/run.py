#!/usr/bin/env python3
"""Recorded VMD deployment and bounded comparison experiments on the edge."""
import datetime as dt
import json
from pathlib import Path
import shlex
import subprocess
import time

ROOT = Path(__file__).resolve().parent
HOST = 'infonetworking@100.111.253.60'
OPTIONS = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15',
           '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3']
EDGE = '/home/infonetworking/csi-zkp'
PACKAGE_NAME = 'vmd-comparison-20261019-v2'
PACKAGE = EDGE + '/packages/' + PACKAGE_NAME
CASES = [('A', 'csi_20261005_115619.csi'), ('B', 'csi_20261005_115523.csi'), ('C', 'csi_20260907_185130.csi')]


def main():
    run_id = 'vmd-' + dt.datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')
    out = ROOT / run_id
    out.mkdir(exist_ok=False)
    (out / 'revision.json').write_text(json.dumps(dict(
        revision=2, supersedes='vmd-20261019T123127',
        corrections=['Use complete modal CSI width instead of eight-series edge loader',
                     'Keep compact 2 Hz Lomb-Scargle search strictly below 1 Hz Nyquist frequency'],
        original_results_preserved=True), indent=2))
    remote_out = EDGE + '/results/' + run_id
    steps = []

    def record(title, command):
        sid = len(steps) + 1
        logname = f'step-{sid:02d}.txt'
        item = dict(step=sid, title=title, argv=command, log=logname, status='running',
                    started_at=dt.datetime.now().astimezone().isoformat())
        steps.append(item)
        (out / 'execution.json').write_text(json.dumps(steps, ensure_ascii=False, indent=2))
        started = time.perf_counter()
        print(f'STEP {sid}: {title}\n{shlex.join(command)}', flush=True)
        with (out / logname).open('w') as log:
            log.write(shlex.join(command) + '\n')
            log.flush()
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
                code = process.wait()
        item.update(status='passed' if code == 0 else 'failed', exit_code=code,
                    seconds=time.perf_counter() - started, ended_at=dt.datetime.now().astimezone().isoformat())
        (out / 'execution.json').write_text(json.dumps(steps, ensure_ascii=False, indent=2))
        if code:
            raise SystemExit(f'Failed step {sid}; records retained at {out}')

    def remote(title, script):
        prefix = 'set -euo pipefail; umask 077; source ' + EDGE + '/env.sh; '
        record(title, ['ssh', *OPTIONS, HOST, 'bash -c ' + shlex.quote(prefix + script)])

    remote('導入前の環境・データハッシュの記録',
           f'test ! -e {PACKAGE}; test ! -e {remote_out}; mkdir {remote_out}; '
           f'python3 -m pip freeze > {remote_out}/freeze-before.txt; free -h; '
           f'ps -C PicoScenes -o pid,etime,%cpu,%mem,comm; '
           'sha256sum ' + ' '.join('/home/infonetworking/csi_data/main/' + f for _, f in CASES) +
           f' > {remote_out}/sources.sha256; cat {remote_out}/sources.sha256')
    for name, version in [('joblib', '1.4.2'), ('threadpoolctl', '3.5.0'), ('scikit-learn', '1.5.2'), ('vmdpy', '0.2')]:
        remote(f'{name} {version} のインストール（既存依存を更新しない）',
               f'python3 -m pip install --only-binary=:all: --no-deps {name}=={version}; python3 -m pip show {name}')
    remote('依存関係・既存NumPy/SciPyの確認', 'python3 -m pip check; python3 -c "import numpy,scipy,sklearn,vmdpy; '
           'print(numpy.__version__,scipy.__version__,sklearn.__version__); print(vmdpy.__file__)"')
    record('VMD配布物の作成・ハッシュ記録', ['python3', str(ROOT / 'build_package.py')])
    record('VMD回路・証明鍵・比較コードの転送', ['scp', *OPTIONS,
           str(ROOT / 'artifacts' / (PACKAGE_NAME + '.tar.gz')),
           str(ROOT / 'artifacts' / (PACKAGE_NAME + '.tar.gz.sha256')), HOST + ':' + EDGE + '/downloads/'])
    check = 'import hashlib,json,pathlib; p=pathlib.Path(' + repr(PACKAGE) + '); m=json.loads((p/"MANIFEST.json").read_text()); ' \
            'assert all(hashlib.sha256((p/n).read_bytes()).hexdigest()==h for n,h in m.items()); print("manifest OK",len(m))'
    remote('アーカイブと全ファイルの整合性検査・配置', f'cd {EDGE}/downloads; '
           f'sha256sum --check {PACKAGE_NAME}.tar.gz.sha256; test ! -e {PACKAGE}; '
           f'tar -xzf {PACKAGE_NAME}.tar.gz -C {EDGE}/packages; python3 -c ' + shlex.quote(check))
    remote('共通前処理・15 BPM・ゼロ信号・入力範囲の単体テスト',
           f'export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1; cd {PACKAGE}; python3 -m unittest -v test_worker')
    common = 'export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1; '
    for name, argument in [('synthetic-15', '--synthetic-hz 0.25'), ('synthetic-30', '--synthetic-hz 0.5'), ('synthetic-48', '--synthetic-hz 0.8')] + \
                          [('real-' + case, '--source /home/infonetworking/csi_data/main/' + filename) for case, filename in CASES]:
        remote(name + '：LS/VMD解析・近似VMD証明・判定改変拒否', common +
               f'/usr/bin/time -v -o {remote_out}/{name}.time.txt python3 {PACKAGE}/worker.py {argument} --output {remote_out}/{name}')
    remote('既存Lomb–Scargleの回帰テスト・元データ保全・依存固定',
           f'{EDGE}/packages/lomb_scargle_e2e/bin/self_test.sh; sha256sum --check {remote_out}/sources.sha256; '
           f'python3 -m pip freeze > {remote_out}/freeze-after.txt; python3 -m pip check; '
           f'ps -C PicoScenes -o pid,etime,%cpu,%mem,comm; python3 -c ' + shlex.quote(check))
    for filename in ('sources.sha256', 'freeze-before.txt', 'freeze-after.txt'):
        record('報告用メタデータ回収：' + filename, ['scp', *OPTIONS, f'{HOST}:{remote_out}/{filename}', str(out / filename)])
    for name in ('synthetic-15', 'synthetic-30', 'synthetic-48', 'real-A', 'real-B', 'real-C'):
        (out / name).mkdir()
        record('結果メタデータ回収：' + name, ['scp', *OPTIONS, f'{HOST}:{remote_out}/{name}/summary.json', str(out / name / 'summary.json')])
        record('プロセス時間・RSS回収：' + name, ['scp', *OPTIONS, f'{HOST}:{remote_out}/{name}.time.txt', str(out / (name + '.time.txt'))])
    (out / 'locations.json').write_text(json.dumps(dict(package=PACKAGE, remote_results=remote_out, run_id=run_id), indent=2))
    print('REPORT_DIRECTORY=' + str(out), flush=True)


if __name__ == '__main__':
    main()
