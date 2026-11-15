#!/usr/bin/env python3
"""Package pinned existing VMD artifacts with separately versioned experiment code."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent.parent.parent
OUT = ROOT / 'artifacts'
PACKAGE = OUT / 'vmd-comparison-20261019-v2'


def main():
    PACKAGE.mkdir(parents=True, exist_ok=False)
    files = {
        'worker.py': ROOT / 'worker.py',
        'test_worker.py': ROOT / 'test_worker.py',
        'vendor/breathing_pipeline.py': REPO / 'backend/app/services/breathing_pipeline.py',
        'vendor/vmd_approx_reference.py': REPO / 'zkp/scripts/vmd_approx_reference.py',
        'artifacts/csi_vmd_approx.wasm': REPO / 'zkp/build/csi_vmd_approx_js/csi_vmd_approx.wasm',
        'artifacts/generate_witness.js': REPO / 'zkp/build/csi_vmd_approx_js/generate_witness.js',
        'artifacts/witness_calculator.js': REPO / 'zkp/build/csi_vmd_approx_js/witness_calculator.js',
        'artifacts/csi_vmd_approx_final.zkey': REPO / 'zkp/keys/csi_vmd_approx_final.zkey',
        'artifacts/verification_key.json': REPO / 'zkp/keys/csi_vmd_approx_verification_key.json',
        'source/csi_vmd_approx.circom': REPO / 'zkp/circuits/csi_vmd_approx.circom',
    }
    manifest = {}
    for name, source in files.items():
        dest = PACKAGE / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        manifest[name] = hashlib.sha256(dest.read_bytes()).hexdigest()
    provenance = dict(git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
                      artifact_rebuilt=False, source_to_artifact_correspondence='Not recompiled; checked by proof verification and integer-reference tests',
                      reuse='Existing WASM/zkey/VK. No new trusted setup or changes to backend source.', files=manifest)
    (PACKAGE / 'PROVENANCE.json').write_text(json.dumps(provenance, indent=2))
    manifest['PROVENANCE.json'] = hashlib.sha256((PACKAGE / 'PROVENANCE.json').read_bytes()).hexdigest()
    (PACKAGE / 'MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    archive = OUT / (PACKAGE.name + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as tar:
        tar.add(PACKAGE, arcname=PACKAGE.name)
    sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    (OUT / (archive.name + '.sha256')).write_text(f'{sha}  {archive.name}\n')
    print(json.dumps(dict(archive=str(archive), bytes=archive.stat().st_size, sha256=sha, files=len(manifest)), indent=2))


if __name__ == '__main__':
    main()
