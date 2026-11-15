#!/usr/bin/env python3
"""Bundle evidence and deliver a new report directory without overwriting old runs."""

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def main():
    out = Path(sys.argv[1]).resolve()
    if not re.fullmatch(r'baseline-\d{8}T\d{6}', out.name):
        raise SystemExit('Unexpected report directory name')
    validation = json.loads((out / 'report-validation.json').read_text())
    assert validation['passed']
    files = {p.relative_to(out).as_posix(): p for p in out.rglob('*')
             if p.is_file() and p.name not in {'report-bundle.zip', 'report-manifest.json', 'delivery.json'}}
    assert not any(name.startswith('proofs/') or Path(name).suffix in {'.csi', '.wtns', '.npz'} for name in files)
    for p in out.parent.iterdir():
        if p.is_file() and p.suffix in {'.py', '.cjs'}:
            files['scripts/' + p.name] = p
    manifest = {name: hashlib.sha256(p.read_bytes()).hexdigest() for name, p in files.items()}
    manifest_path = out / 'report-manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    archive = out / 'report-bundle.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for name, p in sorted(files.items()):
            bundle.write(p, name)
        bundle.write(manifest_path, manifest_path.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    destination = '/home/infonetworking/csi-zkp/reports/' + out.name
    remote_archive = destination + '.zip'
    host = 'infonetworking@100.111.253.60'
    options = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15']
    actions = [
        ['ssh', *options, host, f'test ! -e {destination} && test ! -e {remote_archive}'],
        ['scp', *options, str(archive), f'{host}:{remote_archive}'],
        ['ssh', *options, host, f"set -eu; umask 077; echo '{digest}  {remote_archive}' | sha256sum --check -; "
         f'mkdir {destination}; /usr/bin/python3 -m zipfile -e {remote_archive} {destination}; '
         f'test -s {destination}/report.html; test -s {destination}/report.pdf'],
    ]
    record = dict(archive=archive.name, sha256=digest, bytes=archive.stat().st_size, remote=destination, steps=[])
    for command in actions:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        record['steps'].append(dict(argv=command, exit_code=result.returncode, output=result.stdout))
        (out / 'delivery.json').write_text(json.dumps(record, indent=2))
        print(result.stdout, end='', flush=True)
        result.check_returncode()
    record['delivered'] = True
    (out / 'delivery.json').write_text(json.dumps(record, indent=2))
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
