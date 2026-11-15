#!/usr/bin/env python3
"""Bundle both experiment histories and report assets, excluding private inputs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def main():
    out = Path(sys.argv[1]).resolve()
    if not re.fullmatch(r'vmd-\d{8}T\d{6}', out.name):
        raise SystemExit('Invalid run directory')
    assert json.loads((out / 'report-validation.json').read_text())['passed']
    files = {p.relative_to(out).as_posix(): p for p in out.rglob('*')
             if p.is_file() and p.name not in {'report-bundle.zip', 'report-manifest.json', 'delivery.json'}}
    assert not any(Path(n).suffix in {'.csi', '.wtns', '.npz', '.wasm', '.zkey'} for n in files)
    assert not any('proof' in Path(n).parts for n in files)
    for p in out.parent.iterdir():
        if p.is_file() and p.suffix in {'.py', '.cjs'}:
            files['reproduce/' + p.name] = p
    for revision, name in [('v1', 'vmd-comparison-20261019'), ('v2', 'vmd-comparison-20261019-v2')]:
        package = out.parent / 'artifacts' / name
        for filename in ('worker.py', 'MANIFEST.json', 'PROVENANCE.json'):
            files[f'reproduce/{revision}/{filename}'] = package / filename
    manifest = {n: hashlib.sha256(p.read_bytes()).hexdigest() for n, p in files.items()}
    manifest_file = out / 'report-manifest.json'
    manifest_file.write_text(json.dumps(manifest, indent=2))
    archive = out / 'report-bundle.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, p in sorted(files.items()):
            z.write(p, name)
        z.write(manifest_file, manifest_file.name)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    host = 'infonetworking@100.111.253.60'
    destination = '/home/infonetworking/csi-zkp/reports/' + out.name
    remote_archive = destination + '.zip'
    options = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=15']
    commands = [
        ['ssh', *options, host, f'test ! -e {destination} && test ! -e {remote_archive}'],
        ['scp', *options, str(archive), f'{host}:{remote_archive}'],
        ['ssh', *options, host, f"set -eu; umask 077; echo '{digest}  {remote_archive}' | sha256sum --check -; "
         f'mkdir {destination}; /usr/bin/python3 -m zipfile -e {remote_archive} {destination}; test -s {destination}/report.pdf'],
    ]
    delivery = dict(sha256=digest, bytes=archive.stat().st_size, destination=destination, steps=[])
    for command in commands:
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        delivery['steps'].append(dict(argv=command, exit_code=result.returncode, output=result.stdout))
        (out / 'delivery.json').write_text(json.dumps(delivery, indent=2))
        print(result.stdout, end='', flush=True)
        result.check_returncode()
    delivery['delivered'] = True
    (out / 'delivery.json').write_text(json.dumps(delivery, indent=2))
    print(json.dumps(delivery, indent=2))


if __name__ == '__main__':
    main()
