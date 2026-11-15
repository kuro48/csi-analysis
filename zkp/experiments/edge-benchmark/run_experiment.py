#!/usr/bin/env python3
"""Record deployment/execution and collect only non-CSI benchmark evidence."""

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


def main():
    run_id = 'baseline-' + dt.datetime.now().astimezone().strftime('%Y%m%dT%H%M%S')
    out = ROOT / run_id
    out.mkdir(exist_ok=False)
    remote_script = f'/home/infonetworking/csi-zkp/scripts/{run_id}.py'
    remote_results = f'/home/infonetworking/csi-zkp/results/benchmarks/{run_id}'
    actions = []

    def record(title, command):
        index = len(actions) + 1
        started = time.perf_counter()
        item = dict(step=index, title=title, argv=command, started_at=dt.datetime.now().astimezone().isoformat())
        actions.append(item)
        (out / 'execution.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2))
        print(f'STEP {index}: {title}\n{shlex.join(command)}', flush=True)
        logname = f'step-{index:02d}.txt'
        with (out / logname).open('w') as log:
            log.write(shlex.join(command) + '\n')
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as process:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    print(line, end='', flush=True)
                code = process.wait()
        item.update(exit_code=code, elapsed_seconds=time.perf_counter() - started, log=logname,
                    ended_at=dt.datetime.now().astimezone().isoformat())
        (out / 'execution.json').write_text(json.dumps(actions, ensure_ascii=False, indent=2))
        if code:
            raise SystemExit(f'Step {index} failed: {code}; logs retained at {out}')

    record('集計・再現性チェックの単体テスト', ['python3', '-m', 'unittest', 'discover', '-s', str(ROOT), '-v'])
    record('エッジ側の新規配置先を確認', ['ssh', *OPTIONS, HOST, f'test ! -e {remote_script} && test ! -e {remote_results}'])
    record('測定スクリプトを配置（新規ツールの導入なし）', ['scp', *OPTIONS, str(ROOT / 'benchmark.py'), f'{HOST}:{remote_script}'])
    record('既存回路の反復測定：ウォームアップ3回＋測定15回',
           ['ssh', *OPTIONS, HOST, f'bash -c {shlex.quote("source /home/infonetworking/csi-zkp/env.sh && python3 " + remote_script + " --run-id " + run_id + " --repetitions 5")}'])
    for filename in ('protocol.json', 'summary.json', 'trials.csv', 'progress.json', 'logs', 'timings'):
        record(f'報告用記録の回収：{filename}', ['scp', *OPTIONS, '-r', f'{HOST}:{remote_results}/{filename}', str(out / filename)])
    print(f'LOCAL_REPORT_DIR={out}\nREMOTE_RESULTS_DIR={remote_results}', flush=True)


if __name__ == '__main__':
    main()
