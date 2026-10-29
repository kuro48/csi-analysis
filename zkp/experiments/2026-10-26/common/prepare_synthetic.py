"""Known-target amplitude-modulated CSI controls with a fixed random seed.
These are algorithm controls, never evidence of real physiological accuracy.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from scipy.signal import resample_poly
from sklearn.decomposition import PCA
from prepare_data import load_pipeline, OUT

def main():
    p=load_pipeline(); dest=OUT/'synthetic';dest.mkdir(exist_ok=True)
    rng=np.random.default_rng(20261026); t=np.arange(4800)/100
    cases=[]
    for bpm in (9,12,18):
        for noise in (0.02,0.15):
            phase=rng.uniform(-np.pi,np.pi,32)
            gain=np.linspace(.6,1.4,32)
            latent=np.sin(2*np.pi*bpm/60*t)
            amp=10+gain[None,:]*latent[:,None]+noise*rng.standard_normal((len(t),32))
            csi=amp*np.exp(1j*phase)[None,:]
            selected,indices,snr=p.select_subcarriers_by_snr(amp,100,.1,1.,32)
            filtered=p.bandpass_filter(selected,100,.1,1.)
            pcs=PCA(n_components=3,svd_solver='full').fit_transform(filtered)
            pc,index,scores=p.select_respiration_pc(pcs,100,.1,1.)
            waveform96=resample_poly(pc,1,50)
            waveform128=np.pad(waveform96,(0,32));waveform128-=waveform128.mean()
            signal128=np.asarray(p.prepare_vmd_approx_input(pc)['waveform'],dtype=np.int64)
            case_id=f'synthetic_bpm{bpm}_noise{noise:.2f}'
            np.savez_compressed(dest/(case_id+'.npz'),csi_complex=csi,
                                timestamps_ns=np.rint(t*1e9).astype(np.int64),time_seconds=t,
                                waveform128=waveform128,signal128=signal128,waveform96=waveform96,
                                times128=np.arange(128)/2,pc100=pc,pcs100=pcs,
                                target_bpm=np.array(float(bpm)),latent_waveform96=np.sin(2*np.pi*bpm/60*np.arange(96)/2))
            cases.append({'window_id':case_id,'npz':str(dest/(case_id+'.npz')),'target_bpm':bpm,
                          'noise_std':noise,'amplitude_dc':10,'modulation_gain_range':[.6,1.4],
                          'n_columns':32,'physical_duration_seconds':48,'vmd_padding_samples':32,
                          'pca_index_zero_based':index,'pc_scores':list(map(float,scores))})
    (dest/'manifest.json').write_text(json.dumps({'seed':20261026,'type':'synthetic controls, not human recordings',
              'model':'CSI_j(t) = [10 + gain_j sin(2*pi*target_bpm/60*t) + iid Gaussian noise] exp(i phase_j)',
              'preprocessing':'same100Hz bandpass/PCA/resample/zero-pad as common real windows','cases':cases},indent=2))
if __name__=='__main__':main()
