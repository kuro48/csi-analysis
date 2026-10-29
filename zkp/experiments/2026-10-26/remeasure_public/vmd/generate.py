"""Generate each comparison circuit with actual public intermediate outputs.

No compiled artifacts/public/proofs from the earlier diagnostic are reused.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
DATE=HERE.parents[1]
ROOT=HERE.parents[4]
sys.path.insert(0,str(DATE/'vmd'))
from generate_variant import generate as generate_base
from model import INITIAL_CENTERS
FIELD=21888242871839275222246405745257275088548364400416034343698204186575808495617
K_VALUES=[1,2,3,4,5,8]
R_VALUES=[1,2,4,8,16,32]


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def configurations():
    result=[dict(id=f'k{k}_r{r}',modes=k,iterations=r,initial_centers=INITIAL_CENTERS[:k]) for k in K_VALUES for r in R_VALUES]
    result.append(dict(id='k3_r4_centers8_16_24',modes=3,iterations=4,initial_centers=[8,16,24]))
    return result


def estimate(config):
    k,r=config['modes'],config['iterations']
    constraints=72876+20589*k*r+6931*k
    public=259+126*k*r+(r+1)*k
    power=(constraints+public).bit_length()
    return dict(estimated_constraints=constraints,public_signal_count=public,minimum_ptau_power_estimate=power,
                supported_by_ptau21_estimate=power<=21,
                estimate_basis='Fit from measured original K1R1/K3R4/K5R8, public promotion adds K; actual compile required',
                estimated_peak_config_artifact_bytes=constraints*1400,
                estimated_retained_run_outputs_bytes=10*public*650)


def generate(config):
    k,r=config['modes'],config['iterations']
    directory=HERE/config['id'];directory.mkdir(parents=True,exist_ok=True)
    circuit=directory/f"vmd_{config['id']}_public.circom"
    generate_base(k,r,circuit,config['initial_centers'])
    base=circuit.read_text()
    declaration=f'''
// Public intermediates belong to THIS measured comparison circuit.
signal output debugWaveform[128];
signal output debugDftReal[63];
signal output debugDftImag[63];
signal output debugModeReal[{r}][{k}][63];
signal output debugModeImag[{r}][{k}][63];
signal output debugCenters[{r+1}][{k}];
'''
    copies=f'''
for(var dt=0;dt<128;dt++) debugWaveform[dt] <== waveform[dt];
for(var dj=0;dj<63;dj++) {{debugDftReal[dj] <== fc[dj];debugDftImag[dj] <== fs[dj];}}
for(var dr=0;dr<{r};dr++) for(var dk=0;dk<{k};dk++) for(var dj=0;dj<63;dj++) {{
 debugModeReal[dr][dk][dj] <== ur[dr][dk][dj];
 debugModeImag[dr][dk][dj] <== ui[dr][dk][dj];
}}
for(var dr=0;dr<{r+1};dr++) for(var dk=0;dk<{k};dk++) debugCenters[dr][dk] <== center[dr][dk];
'''
    marker=' signal output intermediateHash;';closing='}component main {public [parentCommitment]}=V();'
    assert base.count(marker)==base.count(closing)==1
    circuit.write_text(base.replace(marker,marker+declaration).replace(closing,copies+closing))
    groups=[('isNormal',[],'isNormal',False),('estimatedFrequencyBin',[],'estimatedFrequencyBin',False),
      ('selectedMode0based',[],'selectedMode0based',False),('intermediateHash',[],'intermediateHash',False),
      ('debugWaveform',[128],'waveform',True),('debugDftReal',[63],'fc',True),('debugDftImag',[63],'fs',True),
      ('debugModeReal',[r,k,63],'ur',True),('debugModeImag',[r,k,63],'ui',True),
      ('debugCenters',[r+1,k],'center',False),('parentCommitment',[],'parentCommitment',False)]
    spans=[];offset=0
    for name,shape,internal,signed in groups:
        count=math.prod(shape)
        spans.append(dict(name=name,shape=shape,public_start_index_zero_based=offset,
          public_end_index_exclusive=offset+count,count=count,decode_signed=signed,actual_internal_source=internal))
        offset+=count
    schema=dict(config=config,circuit=circuit.name,field_modulus=str(FIELD),public_signal_count=offset,
      circuit_sha256=sha256(circuit),groups=spans,samples=128,sample_rate_hz=2,trig_scale=1000,
      array_order='row-major, rightmost index fastest',public_source_policy='Only this config/run Groth16 public.json may be rendered',
      inverse_dft='Host visualization only: bins1..63=(real-i*positive_sine)/1000, DC=Nyquist=0, irfft128')
    (directory/'schema.json').write_text(json.dumps(schema,indent=2))
    return directory


def plan():
    configs=[dict(**c,**estimate(c),status='source_prepared_not_executed') for c in configurations()]
    return dict(real_windows=8,proofs_per_config=10,representative='csi_20260526_034004_w0',
      repeat_design='Each of eight Raw files once, representative receives two additional proofs; all timings are per-run',
      data_scope='real only; no physiological ground truth; no synthetic cases',
      configurations=configs,estimated_keep_all_artifact_bytes=sum(c['estimated_peak_config_artifact_bytes'] for c in configs),
      disk_policy='Process one configuration at a time. Optional prune only its generated build/zkeys after all 10 verified run artifacts/hashes are retained.',
      unavailable_configs_policy='Resource-limit or unavailable ptau is explicit; unexecuted conditions never become successful measurements')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config');args=parser.parse_args()
    configs=configurations()
    for c in configs:
        if args.config is None or args.config==c['id']:generate(c)
    (HERE/'plan.json').write_text(json.dumps(plan(),indent=2))
    print('Source/schema preparation only; no compile/setup/proof performed')
