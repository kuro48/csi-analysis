"""Prepare a representative local input and independent numerical checks for later witness export."""
import hashlib
import json
import secrets
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
DATE=HERE.parents[1]
sys.path.insert(0,str(DATE/'vmd'))
from model import COS,SIN,decompose


def prepare():
    source=DATE/'common/windows/csi_20260526_034004_w0.npz'
    wave=np.load(source)['signal128'].astype(np.int64)
    input_path=HERE/'input.json'
    circuit_input=json.loads(input_path.read_text()) if input_path.exists() else dict(waveform=wave.tolist(),commitmentNonce=str(secrets.randbits(128)),parentCommitment='0')
    if circuit_input['waveform'] != wave.tolist():
        raise ValueError('Existing diagnostic input differs from the selected source; preserve old artifacts before changing it')
    (HERE/'input.json').write_text(json.dumps(circuit_input,indent=2))
    stages=[decompose(wave,3,r) for r in [1,2,3,4]]
    reference=dict(debugWaveform=wave.tolist(),debugDftReal=(COS@wave).tolist(),debugDftImag=(SIN@wave).tolist(),
      debugModeReal=[[[v[0] for v in mode] for mode in stage['spectra']] for stage in stages],
      debugModeImag=[[[v[1] for v in mode] for mode in stage['spectra']] for stage in stages],
      debugCenters=[[8,24,48]]+[stage['centers'] for stage in stages],
      isNormal=int(stages[-1]['is_normal']),estimatedFrequencyBin=stages[-1]['peak_bin'],
      selectedMode0based=stages[-1]['selected_mode'],parentCommitment=0)
    (HERE/'reference_for_validation.json').write_text(json.dumps(reference,indent=2))
    manifest=dict(source_window=source.name,source_npz_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
      observed_seconds=48,padded_samples=32,sample_rate_hz=2,
      input_sha256=hashlib.sha256((HERE/'input.json').read_bytes()).hexdigest(),
      reference_scope='Host recomputation for testing only. Display/export must use circuit public outputs, not this file.',
      privacy='Diagnostic circuit intentionally exposes waveform and intermediate values. Nonce remains a private input.')
    (HERE/'input_manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

if __name__=='__main__':print(json.dumps(prepare(),indent=2))
