"""Decode actual public outputs; inverse DFT is a host-side visualization transform."""
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def export():
    schema=json.loads((HERE/'public_schema.json').read_text())
    public=json.loads((HERE/'public.json').read_text())
    if len(public)!=schema['public_signal_count']:
        raise ValueError('Unexpected public signal count')
    prime=int(schema['field_modulus'])
    decoded={}
    for group in schema['groups']:
        values=[int(x) for x in public[group['public_start_index_zero_based']:group['public_end_index_exclusive']]]
        if any(x<0 or x>=prime for x in values):raise ValueError('Noncanonical field element')
        if group['decode_signed']:values=[x-prime if x>prime//2 else x for x in values]
        if group['shape']:decoded[group['name']]=np.asarray(values,dtype=np.int64).reshape(group['shape'])
        else:decoded[group['name']]=values[0]
    def inverse(real,imag):
        spectrum=np.zeros(65,dtype=complex)
        spectrum[1:64]=(np.asarray(real)-1j*np.asarray(imag))/1000
        return np.fft.irfft(spectrum,n=128)
    def power(real,imag):
        return (np.asarray(real,dtype=float)**2+np.asarray(imag,dtype=float)**2)/1e6
    input_wave=decoded['debugWaveform']
    stages=[]
    for r in range(4):
        modes=[]
        for k in range(3):
            real=decoded['debugModeReal'][r,k];imag=decoded['debugModeImag'][r,k]
            modes.append(dict(mode_index_zero_based=k,center_bin_before=int(decoded['debugCenters'][r,k]),
              center_bin_after=int(decoded['debugCenters'][r+1,k]),real_coefficients_public=real.tolist(),
              positive_sine_coefficients_public=imag.tolist(),power_off_circuit=power(real,imag).tolist(),
              waveform_inverse_dft_off_circuit=inverse(real,imag).tolist()))
        reconstruction=np.sum([m['waveform_inverse_dft_off_circuit'] for m in modes],axis=0)
        stages.append(dict(iteration_one_based=r+1,modes=modes,sum_modes_off_circuit=reconstruction.tolist(),
          residual_off_circuit=(input_wave-reconstruction).tolist()))
    trace=dict(circuit=schema['circuit'],source='Actual public.json extracted from circuit witness; not reference_for_validation.json',
      input_manifest=json.loads((HERE/'input_manifest.json').read_text()),
      exposure='Diagnostic public outputs expose the waveform and every intermediate listed here.',
      visualization_scope='Inverse DFT, power, sums and residuals are computed outside the circuit for visualization; they are not additional proven circuit outputs.',
      inverse_dft_convention='complex bins1..63=(real-1j*positive_sine)/1000; DC=Nyquist=0; irfft(n=128)',
      units='Input is normalized integer amplitude in [-100,100], not physical respiration amplitude. Spectral coefficients use trig scale1000.',
      time_seconds=(np.arange(128)/2).tolist(),observed_sample_mask=(np.arange(128)<96).tolist(),
      frequency_hz=(np.arange(1,64)*2/128).tolist(),frequency_bpm=(np.arange(1,64)*120/128).tolist(),
      input_waveform_public=input_wave.tolist(),
      dft=dict(real_coefficients_public=decoded['debugDftReal'].tolist(),positive_sine_coefficients_public=decoded['debugDftImag'].tolist(),
        power_off_circuit=power(decoded['debugDftReal'],decoded['debugDftImag']).tolist(),
        waveform_inverse_dft_off_circuit=inverse(decoded['debugDftReal'],decoded['debugDftImag']).tolist()),
      center_trajectory_public=decoded['debugCenters'].tolist(),stages=stages,
      result=dict(is_normal=bool(decoded['isNormal']),frequency_bin=decoded['estimatedFrequencyBin'],
        bpm=decoded['estimatedFrequencyBin']*120/128,selected_mode_zero_based=decoded['selectedMode0based'],
        intermediate_hash=str(decoded['intermediateHash']),parent_commitment=str(decoded['parentCommitment'])))
    (HERE/'trace.json').write_text(json.dumps(trace,indent=2))
    return trace

if __name__=='__main__':
    trace=export();print(json.dumps(trace['result']))
