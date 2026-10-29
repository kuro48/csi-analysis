"""Expose actual production VMD internal signals in a separate diagnostic circuit.

This script only writes source/schema/input files. It never compiles or proves.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
CIRCUIT_NAME = 'vmd_k3_r4_public_trace'
FIELD = '21888242871839275222246405745257275088548364400416034343698204186575808495617'

GROUPS = [
    ('isNormal', [], 'isNormal', False),
    ('estimatedFrequencyBin', [], 'estimatedFrequencyBin', False),
    ('selectedMode0based', [], 'selectedMode0based', False),
    ('intermediateHash', [], 'intermediateHash', False),
    ('debugWaveform', [128], 'waveform', True),
    ('debugDftReal', [63], 'fc', True),
    ('debugDftImag', [63], 'fs', True),
    ('debugModeReal', [4, 3, 63], 'ur', True),
    ('debugModeImag', [4, 3, 63], 'ui', True),
    ('debugCenters', [5, 3], 'center', False),
    ('parentCommitment', [], 'parentCommitment', False),
]


def generate():
    source = ROOT / 'zkp/circuits/csi_vmd_approx.circom'
    original = source.read_text()
    marker = ' signal output intermediateHash;'
    assert original.count(marker) == 1
    declaration = '''
 // DIAGNOSTIC ONLY: these outputs reveal private input and intermediate values.
 signal output debugWaveform[128];
 signal output debugDftReal[63];
 signal output debugDftImag[63];
 signal output debugModeReal[4][3][63];
 signal output debugModeImag[4][3][63];
 signal output debugCenters[5][3];
'''
    copies = '''
// Copy constrained internal signals, never host-supplied recomputations.
for (var dt=0; dt<128; dt++) debugWaveform[dt] <== waveform[dt];
for (var dj=0; dj<63; dj++) {
    debugDftReal[dj] <== fc[dj];
    debugDftImag[dj] <== fs[dj];
}
for (var dr=0; dr<4; dr++) for (var dk=0; dk<3; dk++) for (var dj=0; dj<63; dj++) {
    debugModeReal[dr][dk][dj] <== ur[dr][dk][dj];
    debugModeImag[dr][dk][dj] <== ui[dr][dk][dj];
}
for (var dr=0; dr<5; dr++) for (var dk=0; dk<3; dk++) {
    debugCenters[dr][dk] <== center[dr][dk];
}
'''
    closing = '}component main {public [parentCommitment]}=V();'
    assert original.count(closing) == 1
    generated = original.replace(marker, marker + declaration).replace(closing, copies + closing)
    (HERE / f'{CIRCUIT_NAME}.circom').write_text(generated)
    spans = []
    offset = 0
    for name, shape, internal, signed in GROUPS:
        count = 1
        for dimension in shape:
            count *= dimension
        spans.append(dict(name=name, shape=shape, public_start_index_zero_based=offset,
                          public_end_index_exclusive=offset + count, count=count,
                          witness_start_index_one_based=offset + 1,
                          actual_internal_source=internal, decode_signed=signed,
                          role='public_input' if name == 'parentCommitment' else 'public_output'))
        offset += count
    schema = dict(circuit=CIRCUIT_NAME, modes=3, iterations=4, samples=128, sample_rate_hz=2,
                  dft_bin_numbers=list(range(1,64)), trig_scale=1000,
                  public_signal_count=offset, public_output_count=offset-1,
                  array_order='row-major, rightmost index varies fastest', field_modulus=FIELD,
                  signed_decoding='For signed groups only: int(v)-p if int(v)>p//2 else int(v)',
                  sine_convention='positive-sine coefficient; conventional FFT complex = real - i*imag',
                  source_path=str(source), source_sha256=hashlib.sha256(original.encode()).hexdigest(),
                  circuit_sha256=hashlib.sha256(generated.encode()).hexdigest(), groups=spans)
    (HERE / 'public_schema.json').write_text(json.dumps(schema, indent=2))
    (HERE / 'build').mkdir(exist_ok=True)
    return schema

if __name__ == '__main__':
    schema=generate()
    print(json.dumps(dict(circuit=schema['circuit'],public_outputs=schema['public_output_count'],public_signals=schema['public_signal_count'])))
