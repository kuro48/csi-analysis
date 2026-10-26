"""Decode THIS run's verified proof public values; derived waveforms are off-circuit."""
import json
import sys
import numpy as np
from generate import DATE,FIELD,sha256
sys.path.insert(0,str(DATE/'vmd'))
from model import COS,SIN,decompose


def decode(schema,public):
    if len(public)!=schema['public_signal_count']:raise ValueError('public length')
    out={}
    for g in schema['groups']:
        values=[int(v) for v in public[g['public_start_index_zero_based']:g['public_end_index_exclusive']]]
        if any(v<0 or v>=FIELD for v in values):raise ValueError('Noncanonical public field')
        if g['decode_signed']:values=[v-FIELD if v>FIELD//2 else v for v in values]
        out[g['name']]=np.array(values,dtype=np.int64).reshape(g['shape']) if g['shape'] else values[0]
    return out


def validate_and_trace(config_dir,run_dir,binding):
    schema=json.loads((config_dir/'schema.json').read_text());public=json.loads((run_dir/'public.json').read_text())
    actual=decode(schema,public);config=schema['config'];k,r=config['modes'],config['iterations'];centers=config['initial_centers']
    x=np.array(json.loads((run_dir/'input.json').read_text())['waveform'],dtype=np.int64)
    assert actual['debugWaveform'].tolist()==x.tolist()
    assert actual['debugDftReal'].tolist()==(COS@x).tolist()
    assert actual['debugDftImag'].tolist()==(SIN@x).tolist()
    assert actual['debugCenters'][0].tolist()==centers
    for n in range(r):
        ref=decompose(x,k,n+1,centers)
        assert actual['debugCenters'][n+1].tolist()==ref['centers']
        assert np.stack([actual['debugModeReal'][n],actual['debugModeImag'][n]],axis=-1).tolist()==ref['spectra']
    assert actual['estimatedFrequencyBin']==ref['peak_bin']
    assert actual['selectedMode0based']==ref['selected_mode']
    assert actual['isNormal']==int(ref['is_normal'])
    def inverse(real,imag):
        spec=np.zeros(65,dtype=complex);spec[1:64]=(real-1j*imag)/1000
        return np.fft.irfft(spec,n=128)
    def spectrum(real,imag):
        return dict(real_coefficients_public=real.tolist(),positive_sine_coefficients_public=imag.tolist(),
          power_off_circuit=((real.astype(float)**2+imag.astype(float)**2)/1e6).tolist(),
          waveform_inverse_dft_off_circuit=inverse(real,imag).tolist())
    stages=[]
    for n in range(r):
        modes=[dict(mode_index_zero_based=m,**spectrum(actual['debugModeReal'][n,m],actual['debugModeImag'][n,m])) for m in range(k)]
        total=np.sum([m['waveform_inverse_dft_off_circuit'] for m in modes],axis=0)
        stages.append(dict(iteration_one_based=n+1,modes=modes,sum_modes_off_circuit=total.tolist(),residual_off_circuit=(x-total).tolist()))
    trace=dict(config=config,binding=binding,public_sha256=sha256(run_dir/'public.json'),
      source='This measured run verified Groth16 public.json only; no diagnostic/public reuse',
      display_scope='Inverse DFT/power/sum/residual are off-circuit visualization, not additional proved computations',
      inverse_dft='bins1..63=(real-i*positive_sine)/1000, DC=Nyquist=0, irfft128',
      time_seconds=(np.arange(128)/2).tolist(),observed_sample_mask=(np.arange(128)<96).tolist(),
      frequency_bpm=(np.arange(1,64)*120/128).tolist(),input_waveform_public=actual['debugWaveform'].tolist(),
      dft=spectrum(actual['debugDftReal'],actual['debugDftImag']),center_trajectory_public=actual['debugCenters'].tolist(),stages=stages,
      result=dict(is_normal=bool(actual['isNormal']),bpm=actual['estimatedFrequencyBin']*120/128,
        frequency_bin=actual['estimatedFrequencyBin'],selected_mode_zero_based=actual['selectedMode0based'],
        intermediate_hash=str(actual['intermediateHash']),parent_commitment=str(actual['parentCommitment'])))
    (run_dir/'trace.json').write_text(json.dumps(trace,indent=2))
    return trace['result']
